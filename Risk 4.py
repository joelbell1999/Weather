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
    "pytz",
    "pytesseract",
    "pillow"
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
import pytesseract
from PIL import Image
import io
from typing import Optional, Any

# ---- CONSTANTS ----
API_TIMEOUT = 15  # seconds
CACHE_TTL = 300  # 5 minutes in seconds
DEFAULT_LOCATION = {"lat": 32.9, "lon": -97.3, "label": "DFW Metroplex"}
DEFAULT_METRICS = {
    "cape_jkg": 0,
    "shear_mph": 0,
    "source": "Default Values"
}

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
    """Robust Pivotal Weather scraper with multiple fallback methods"""
    headers = {
        "User-Agent": "DFW Severe Weather Dashboard (Contact: admin@example.com)",
        "Accept-Language": "en-US",
        "Referer": "https://www.pivotalweather.com/"
    }
    
    try:
        # Step 1: Get the main model page to find latest run
        base_url = "https://www.pivotalweather.com/model.php?m=hrrr"
        response = requests.get(base_url, headers=headers, timeout=API_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find latest run time
        run_info = soup.find("div", class_="model-run-info")
        if not run_info:
            raise ValueError("Could not find model run information")
        
        # Step 2: Get CAPE data - try multiple methods
        cape_value = None
        
        # Method 1: Try to get from HTML page
        try:
            cape_url = "https://www.pivotalweather.com/model.php?m=hrrr&p=sfc_cape"
            cape_response = requests.get(cape_url, headers=headers, timeout=API_TIMEOUT)
            cape_soup = BeautifulSoup(cape_response.text, 'html.parser')
            
            # Try multiple selectors for robustness
            for selector in [
                {"class_": "parameter-value", "attrs": {"data-parameter": "cape"}},
                {"class_": "data-value"},
                {"id": "cape-value"}
            ]:
                element = cape_soup.find("div", **selector)
                if element and element.text.strip():
                    match = re.search(r"(\d+)", element.text)
                    if match:
                        cape_value = float(match.group(1))
                        break
        except Exception:
            pass
        
        # Method 2: Try to extract from image
        if cape_value is None:
            try:
                cape_img_url = "https://www.pivotalweather.com/data/models/hrrr/latest/sfc_cape.png"
                img_response = requests.get(cape_img_url, headers=headers, timeout=API_TIMEOUT)
                
                if 'image' in img_response.headers.get('Content-Type', ''):
                    img = Image.open(io.BytesIO(img_response.content))
                    text = pytesseract.image_to_string(img)
                    match = re.search(r"(\d+)", text)
                    if match:
                        cape_value = float(match.group(1))
            except Exception:
                pass
        
        # Method 3: Fallback to default if all else fails
        if cape_value is None:
            cape_value = 0
            st.warning("Using default CAPE value - could not scrape accurate data")
        
        # Step 3: Get Shear data (similar approach)
        shear_value = None
        
        # Method 1: Try to get from HTML page
        try:
            shear_url = "https://www.pivotalweather.com/model.php?m=hrrr&p=shear_06km"
            shear_response = requests.get(shear_url, headers=headers, timeout=API_TIMEOUT)
            shear_soup = BeautifulSoup(shear_response.text, 'html.parser')
            
            for selector in [
                {"class_": "parameter-value", "attrs": {"data-parameter": "shear"}},
                {"class_": "data-value"},
                {"id": "shear-value"}
            ]:
                element = shear_soup.find("div", **selector)
                if element and element.text.strip():
                    match = re.search(r"(\d+)", element.text)
                    if match:
                        shear_value = float(match.group(1)) * 1.15078  # Convert knots to mph
                        break
        except Exception:
            pass
        
        # Method 2: Try to extract from image
        if shear_value is None:
            try:
                shear_img_url = "https://www.pivotalweather.com/data/models/hrrr/latest/shear_06km.png"
                img_response = requests.get(shear_img_url, headers=headers, timeout=API_TIMEOUT)
                
                if 'image' in img_response.headers.get('Content-Type', ''):
                    img = Image.open(io.BytesIO(img_response.content))
                    text = pytesseract.image_to_string(img)
                    match = re.search(r"(\d+)", text)
                    if match:
                        shear_value = float(match.group(1)) * 1.15078  # Convert knots to mph
            except Exception:
                pass
        
        # Method 3: Fallback to default if all else fails
        if shear_value is None:
            shear_value = 25.0
            st.warning("Using default shear value - could not scrape accurate data")
        
        return {
            "cape_jkg": cape_value,
            "shear_mph": shear_value,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": f"Pivotal Weather HRRR {run_info.text.strip()}"
        }
        
    except Exception as e:
        st.warning(f"Scraping attempt failed: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def get_nws_severe_data(lat: float, lon: float) -> Optional[dict[str, Any]]:
    """Get severe weather data from NWS API with robust error handling"""
    try:
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        points_resp = requests.get(points_url, timeout=API_TIMEOUT)
        points_resp.raise_for_status()
        grid_url = points_resp.json()["properties"]["forecastGridData"]
        
        grid_resp = requests.get(grid_url, timeout=API_TIMEOUT)
        grid_resp.raise_for_status()
        data = grid_resp.json()["properties"]
        
        # Safely extract values with multiple fallbacks
        cape = data.get("convectiveAvailablePotentialEnergy", {}).get("values", [{}])[0].get("value", 0)
        wind_gust = data.get("windGust", {}).get("values", [{}])[0].get("value", 0)
        
        return {
            "cape_jkg": cape,
            "shear_mph": wind_gust,
            "source": "National Weather Service",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        st.warning(f"NWS API failed: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def get_openmeteo_severe_data(lat: float, lon: float) -> dict[str, Any]:
    """Reliable fallback data source from Open-Meteo"""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&hourly=cape,windgusts_10m"
            f"&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=auto"
        )
        res = requests.get(url, timeout=API_TIMEOUT).json()
        
        if "hourly" not in res:
            raise ValueError("No hourly data in response")
            
        hourly = res["hourly"]
        current_hour = datetime.now().hour
        
        return {
            "cape_jkg": hourly.get("cape", [0])[current_hour],
            "shear_mph": hourly.get("windgusts_10m", [0])[current_hour],
            "source": "Open-Meteo Forecast",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        st.error(f"Open-Meteo failed: {str(e)}")
        return DEFAULT_METRICS

def get_severe_metrics(lat: float, lon: float) -> dict[str, Any]:
    """Hierarchical data fetching with scraping as first attempt"""
    # 1. Try scraping first
    scraped_data = scrape_pivotal_metrics()
    if scraped_data:
        return scraped_data
    
    # 2. Fallback to NWS API
    nws_data = get_nws_severe_data(lat, lon)
    if nws_data:
        return nws_data
    
    # 3. Final fallback to Open-Meteo
    return get_openmeteo_severe_data(lat, lon)

@st.cache_data(ttl=CACHE_TTL)
def get_hourly_forecast(lat: float, lon: float) -> tuple[Optional[list[dict[str, Any]]], ...]:
    """Get detailed forecast from Open-Meteo"""
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
            raise ValueError("Incomplete forecast data")
            
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
    st.title("Severe Weather Dashboard")
    
    # Get location
    with st.spinner("Detecting location..."):
        lat, lon, label = get_user_location()
    
    st.markdown(f"**Location:** {label}")
    st.map({"lat": [lat], "lon": [lon]})
    
    # Get weather data
    with st.spinner("Fetching weather data..."):
        try:
            metrics = get_severe_metrics(lat, lon)
            forecast = get_hourly_forecast(lat, lon)
            
            if None in forecast:
                st.warning("Partial forecast data available")
                hourly, precip_24h, times, cape_vals, cin_vals, full_times, sunrise, sunset, tz = forecast
                if not hourly:
                    raise ValueError("No hourly forecast data")
            else:
                hourly, precip_24h, times, cape_vals, cin_vals, full_times, sunrise, sunset, tz = forecast
            
            # Set timezone-aware datetime objects
            now = datetime.fromisoformat(full_times[0]).replace(tzinfo=ZoneInfo(tz))
            sunrise = sunrise.replace(tzinfo=ZoneInfo(tz))
            sunset = sunset.replace(tzinfo=ZoneInfo(tz))
            set_background_theme(now, sunrise, sunset)
            
            # Display metrics
            col1, col2 = st.columns(2)
            with col1:
                st.metric("CAPE", f"{metrics['cape_jkg']} J/kg", 
                         help="Convective Available Potential Energy")
            with col2:
                st.metric("0-6km Shear", f"{metrics['shear_mph']:.1f} mph",
                         help="Bulk wind shear (storm organization potential)")
            st.caption(f"Source: {metrics['source']} | Last updated: {metrics['last_updated']}")
            
            # Display Pivotal Weather maps
            st.subheader("Pivotal Weather Model Data")
            map_col1, map_col2 = st.columns(2)
            with map_col1:
                st.image("https://www.pivotalweather.com/data/models/hrrr/latest/sfc_cape.png",
                        caption="Latest HRRR CAPE", use_column_width=True)
            with map_col2:
                st.image("https://www.pivotalweather.com/data/models/hrrr/latest/shear_06km.png",
                        caption="Latest HRRR 0-6km Shear", use_column_width=True)
            
            # Display trends if we have data
            if cape_vals and cin_vals:
                st.subheader("Atmospheric Trends")
                trend_col1, trend_col2 = st.columns(2)
                with trend_col1:
                    st.pyplot(plot_weather_trend(times, cape_vals, "CAPE Trend", "red", "CAPE (J/kg)"))
                with trend_col2:
                    st.pyplot(plot_weather_trend(times, cin_vals, "CIN Trend", "blue", "CIN (J/kg)"))
            
            # Display forecast
            st.subheader("Hourly Forecast")
            for hour in hourly[:12]:  # Show next 12 hours
                with st.expander(hour["time"], expanded=False):
                    cols = st.columns(3)
                    with cols[0]:
                        st.metric("Temperature", f"{hour['temperature']}°F")
                        st.metric("Dewpoint", f"{hour['dewpoint']}°F")
                    with cols[1]:
                        st.metric("Wind", f"{hour['windSpeed']}/{hour['windGusts']} mph")
                        st.metric("Humidity", f"{hour['humidity']}%")
                    with cols[2]:
                        st.metric("Precip", f"{hour['precipitation']} in")
                        st.metric("Cloud Cover", f"{hour['cloudCover']}%")
            
            # Display precipitation summary if available
            if precip_24h is not None:
                st.subheader(f"24-Hour Precipitation: {precip_24h:.2f} in")
            
        except Exception as e:
            st.error(f"Failed to load weather data: {str(e)}")
            st.info("Default values are being shown. Please try again later.")
            
            # Show default metrics
            col1, col2 = st.columns(2)
            with col1:
                st.metric("CAPE", f"{DEFAULT_METRICS['cape_jkg']} J/kg")
            with col2:
                st.metric("0-6km Shear", f"{DEFAULT_METRICS['shear_mph']:.1f} mph")

if __name__ == "__main__":
    main()
