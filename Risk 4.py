# ---- AUTO-INSTALL MISSING PACKAGES ----
import subprocess
import sys

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

REQUIRED_PACKAGES = [
    ("beautifulsoup4", "bs4"),
    "requests",
    "pandas",
    "geopy",
    "matplotlib",
    "python-dateutil",
    "pytz"
]

for package in REQUIRED_PACKAGES:
    try:
        if isinstance(package, tuple):
            __import__(package[1])
        else:
            __import__(package)
    except ImportError:
        install(package[0] if isinstance(package, tuple) else package)

# ---- CORE IMPORTS ----
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from geopy.distance import geodesic
from bs4 import BeautifulSoup
import re
import time
import matplotlib.pyplot as plt

# ---- TYPE HINTS ----
from typing import Optional, Any  # Still needed for special cases

# ---- CONSTANTS ----
API_TIMEOUT = 15  # seconds
CACHE_TTL = 300  # 5 minutes in seconds
DEFAULT_LOCATION = {"lat": 32.9, "lon": -97.3, "label": "DFW Metroplex"}

# ---- LOCATION FUNCTIONS ----
def get_browser_location() -> Optional[tuple[float, float]]:
    """Attempt to get browser geolocation"""
    st.markdown("""
    <script>
    navigator.geolocation.getCurrentPosition(
        (loc) => {
            const coords = `${loc.coords.latitude},${loc.coords.longitude}`;
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: coords}, "*");
        },
        (err) => {
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: 'geo_failed'}, "*");
        }
    );
    </script>
    """, unsafe_allow_html=True)
    
    location_coords = st.query_params.get("geolocation", [None])[0]
    if location_coords and location_coords != "geo_failed":
        return tuple(map(float, location_coords.split(",")))
    return None

def get_coordinates_from_zip(zip_code: str) -> tuple[float, float, str]:
    """Get coordinates from ZIP code"""
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}", timeout=API_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        place = data["places"][0]
        return float(place["latitude"]), float(place["longitude"]), f"{place['place name']}, {place['state abbreviation']}"
    except Exception:
        return (*DEFAULT_LOCATION.values(),)

def get_coordinates_from_city(city_state: str) -> tuple[float, float, str]:
    """Get coordinates from city/state"""
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_state}&country=US"
        r = requests.get(url, timeout=API_TIMEOUT).json()
        if "results" in r and r["results"]:
            res = r["results"][0]
            return res["latitude"], res["longitude"], res["name"]
        return (*DEFAULT_LOCATION.values(),)
    except Exception:
        return (*DEFAULT_LOCATION.values(),)

def get_user_location() -> tuple[float, float, str]:
    """Get location from user input or browser geolocation"""
    browser_coords = get_browser_location()
    if browser_coords:
        lat, lon = browser_coords
        return lat, lon, "Detected Location (via Browser)"
    
    user_input = st.text_input("Enter ZIP Code or City, State", "76247")
    return get_coordinates_from_zip(user_input) if user_input.isnumeric() else get_coordinates_from_city(user_input)

# ---- WEATHER DATA FUNCTIONS ----
@st.cache_data(ttl=CACHE_TTL)
def scrape_pivotal_metrics() -> Optional[dict[str, Any]]:
    """Scrape CAPE and wind shear from Pivotal Weather"""
    headers = {
        "User-Agent": "DFW Severe Weather Dashboard (Contact: admin@example.com)",
        "Accept-Language": "en-US"
    }
    
    try:
        # Get CAPE page
        cape_url = "https://www.pivotalweather.com/model.php?m=hrrr&p=sfc_cape"
        response = requests.get(cape_url, headers=headers, timeout=API_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract CAPE value (example parsing - adjust selectors as needed)
        cape_value = float(soup.find("div", class_="data-value").text.split()[0])
        
        # Get shear value
        shear_value = 35.0  # Placeholder - implement actual scraping
        return {
            "cape_jkg": cape_value,
            "shear_mph": shear_value,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "Pivotal Weather HRRR"
        }
    except Exception as e:
        st.error(f"⚠️ Scraping failed: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def get_forecast(lat: float, lon: float) -> tuple[Optional[list[dict[str, Any]]], ...]:
    """Get weather forecast from Open-Meteo API"""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,windspeed_10m,windgusts_10m,precipitation,precipitation_probability,"
            f"cloudcover,dewpoint_2m,relative_humidity_2m,cape,convective_inhibition"
            f"&daily=precipitation_sum,sunrise,sunset&past_days=1&forecast_days=1"
            f"&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch&timezone=auto"
        )
        res = requests.get(url, timeout=API_TIMEOUT).json()
        
        if "hourly" not in res or "daily" not in res:
            return (None,) * 9
            
        hourly = res["hourly"]
        timezone = res.get("timezone", "America/Chicago")
        data = []
        
        for i, time in enumerate(hourly["time"]):
            dt = datetime.fromisoformat(time)
            if dt > datetime.now() and len(data) < 12:
                data.append({
                    "time": dt.strftime("%a %I:%M %p"),
                    "temperature": hourly["temperature_2m"][i],
                    "windSpeed": hourly["windspeed_10m"][i],
                    "windGusts": hourly["windgusts_10m"][i],
                    "precipitation": hourly["precipitation"][i],
                    "precipProbability": hourly["precipitation_probability"][i],
                    "cloudCover": hourly["cloudcover"][i],
                    "dewpoint": hourly["dewpoint_2m"][i],
                    "humidity": hourly["relative_humidity_2m"][i],
                    "cape": hourly["cape"][i],
                    "cin": hourly["convective_inhibition"][i]
                })
                
        return (
            data,
            res["daily"]["precipitation_sum"][0],
            [datetime.fromisoformat(t).strftime("%I %p") for t in hourly["time"][:12]],
            hourly["cape"][:12],
            hourly["convective_inhibition"][:12],
            hourly["time"],
            datetime.fromisoformat(res["daily"]["sunrise"][0]),
            datetime.fromisoformat(res["daily"]["sunset"][0]),
            timezone
        )
    except Exception as e:
        st.error(f"Forecast failed: {str(e)}")
        return (None,) * 9

# ---- VISUALIZATION FUNCTIONS ----
def plot_weather_trend(times: list[str], values: list[float],
                      title: str, color: str, ylabel: str) -> plt.Figure:
    """Create a weather trend plot"""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, values, marker="o", color=color, linewidth=2)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time")
    ax.set_title(title)
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

def set_background_theme(now: datetime, sunrise: datetime, sunset: datetime):
    """Set dynamic background based on time of day"""
    if now < sunrise - timedelta(minutes=90) or now > sunset + timedelta(minutes=90):
        bg = "#000000"
    elif sunrise - timedelta(minutes=90) <= now < sunrise - timedelta(minutes=30):
        bg = "#1a1a2e"
    elif sunrise - timedelta(minutes=30) <= now < sunrise:
        bg = "#2c3e50"
    elif sunrise <= now < sunrise + timedelta(minutes=30):
        bg = "#ff914d"
    elif sunset - timedelta(minutes=30) <= now < sunset:
        bg = "#ff914d"
    elif sunset <= now < sunset + timedelta(minutes=30):
        bg = "#2c3e50"
    else:
        bg = "#fff8cc"
        
    st.markdown(f"<style>.stApp {{background-color: {bg};}}</style>", 
                unsafe_allow_html=True)

# ---- MAIN APPLICATION ----
def main():
    # Get location
    with st.spinner("Detecting location..."):
        lat, lon, label = get_user_location()
    
    st.markdown(f"**Location:** {label}")
    st.map({"lat": [lat], "lon": [lon]})
    
    # Get weather data
    with st.spinner("Fetching weather data..."):
        metrics = scrape_pivotal_metrics() or {
            "cape_jkg": 0,
            "shear_mph": 0,
            "source": "Fallback"
        }
        
        forecast = get_forecast(lat, lon)
        if None in forecast:
            st.error("Data unavailable")
            return
            
        hourly, precip_24h, times, cape_vals, cin_vals, full_times, sunrise, sunset, tz = forecast
        
    # Display data
    now = datetime.fromisoformat(full_times[0]).replace(tzinfo=ZoneInfo(tz))
    set_background_theme(now, sunrise.replace(tzinfo=ZoneInfo(tz)), sunset.replace(tzinfo=ZoneInfo(tz)))
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("CAPE", f"{metrics['cape_jkg']} J/kg")
    with col2:
        st.metric("0-6km Shear", f"{metrics['shear_mph']:.1f} mph")
    
    st.pyplot(plot_weather_trend(times, cape_vals, "CAPE Trend", "red", "CAPE (J/kg)"))
    st.pyplot(plot_weather_trend(times, cin_vals, "CIN Trend", "blue", "CIN (J/kg)"))
    
    for hour in hourly:
        with st.expander(hour["time"]):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Temp", f"{hour['temperature']}°F")
                st.metric("Wind", f"{hour['windSpeed']}/{hour['windGusts']} mph")
            with col2:
                st.metric("Precip", f"{hour['precipitation']} in")
                st.metric("Humidity", f"{hour['humidity']}%")

if __name__ == "__main__":
    main()
