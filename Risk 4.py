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
from typing import Optional, Dict, Tuple

# Configuration
API_TIMEOUT = 15  # seconds
CACHE_TTL = 300  # 5 minutes in seconds
DEFAULT_LOCATION = {"lat": 32.9, "lon": -97.3, "label": "DFW Metroplex"}

# Setup Streamlit
st.set_page_config("Severe Weather Dashboard", layout="centered")
st.title("Severe Weather Dashboard")

# --- Location Functions ---
def get_browser_location() -> Optional[Tuple[float, float]]:
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

def get_coordinates_from_zip(zip_code: str) -> Tuple[float, float, str]:
    """Get coordinates from ZIP code using Zippopotam API"""
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}", timeout=API_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        place = data["places"][0]
        return float(place["latitude"]), float(place["longitude"]), f"{place['place name']}, {place['state abbreviation']}"
    except Exception as e:
        st.error(f"Failed to get location from ZIP code: {str(e)}")
        return (*DEFAULT_LOCATION.values(),)

def get_coordinates_from_city(city_state: str) -> Tuple[float, float, str]:
    """Get coordinates from city/state using Open-Meteo geocoding"""
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_state}&country=US"
        r = requests.get(url, timeout=API_TIMEOUT).json()
        if "results" in r and r["results"]:
            res = r["results"][0]
            return res["latitude"], res["longitude"], res["name"]
        return (*DEFAULT_LOCATION.values(),)
    except Exception as e:
        st.error(f"Failed to geocode city: {str(e)}")
        return (*DEFAULT_LOCATION.values(),)

def get_user_location() -> Tuple[float, float, str]:
    """Get location from user input or browser geolocation"""
    browser_coords = get_browser_location()
    if browser_coords:
        lat, lon = browser_coords
        return lat, lon, "Detected Location (via Browser)"
    
    user_input = st.text_input("Enter ZIP Code or City, State", "76247")
    if user_input.isnumeric():
        return get_coordinates_from_zip(user_input)
    else:
        return get_coordinates_from_city(user_input)

# --- Weather Data Functions ---
@st.cache_data(ttl=CACHE_TTL)
def scrape_pivotal_metrics() -> Optional[Dict]:
    """
    Scrapes CAPE and 0-6km wind shear from Pivotal Weather's HRRR model page.
    Returns: {'cape_jkg': float, 'shear_kts': float, 'shear_mph': float, 'source': str}
    """
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
        
        # Extract CAPE value
        cape_div = soup.find("div", class_="parameter-value", 
                           attrs={"data-parameter": "cape"})
        cape_value = float(re.search(r"(\d+)", cape_div.text).group(1))
        
        # Get shear page
        shear_link = soup.find("a", href=re.compile("shear_06km"), 
                             class_="parameter-link")
        if not shear_link:
            raise ValueError("Shear link not found")
            
        shear_url = f"https://www.pivotalweather.com{shear_link['href']}"
        time.sleep(2)  # Respectful delay between requests
        
        shear_response = requests.get(shear_url, headers=headers, timeout=API_TIMEOUT)
        shear_soup = BeautifulSoup(shear_response.text, 'html.parser')
        
        # Extract shear value
        shear_div = shear_soup.find("div", class_="parameter-value", 
                                  attrs={"data-parameter": "shear"})
        shear_kts = float(re.search(r"(\d+)", shear_div.text).group(1))
        
        return {
            "cape_jkg": cape_value,
            "shear_kts": shear_kts,
            "shear_mph": shear_kts * 1.15078,  # Convert to mph
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "Pivotal Weather HRRR"
        }
        
    except Exception as e:
        st.error(f"⚠️ Scraping failed: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def get_nws_severe_data(lat: float, lon: float) -> Optional[Dict]:
    """Get severe weather data from NWS API"""
    try:
        # First get gridpoint
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        points_resp = requests.get(points_url, timeout=API_TIMEOUT)
        points_resp.raise_for_status()
        grid_url = points_resp.json()["properties"]["forecastGridData"]
        
        # Then get forecast data
        grid_resp = requests.get(grid_url, timeout=API_TIMEOUT)
        grid_resp.raise_for_status()
        data = grid_resp.json()["properties"]
        
        return {
            "cape": data["convectiveAvailablePotentialEnergy"]["values"][0]["value"],
            "shear": data["windGust"]["values"][0]["value"],
            "source": "NWS API"
        }
    except Exception as e:
        st.warning(f"NWS API failed: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def get_forecast(lat: float, lon: float) -> Tuple[Optional[Dict], ...]:
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
                
        times = [datetime.fromisoformat(t).strftime("%I %p") for t in hourly["time"][:12]]
        cape_vals = hourly["cape"][:12]
        cin_vals = hourly["convective_inhibition"][:12]
        daily = res["daily"]
        
        return (
            data,
            daily["precipitation_sum"][0],
            times,
            cape_vals,
            cin_vals,
            hourly["time"],
            datetime.fromisoformat(daily["sunrise"][0]),
            datetime.fromisoformat(daily["sunset"][0]),
            timezone
        )
    except Exception as e:
        st.error(f"Failed to get forecast data: {str(e)}")
        return (None,) * 9

def get_severe_metrics(lat: float, lon: float) -> Dict:
    """Hierarchical data fetching with scraping as last resort"""
    # Try Pivotal scraping first
    pivotal_data = scrape_pivotal_metrics()
    if pivotal_data:
        return pivotal_data
    
    # Fallback to NWS API
    nws_data = get_nws_severe_data(lat, lon)
    if nws_data:
        st.warning("Using NWS data (Pivotal unavailable)")
        return {
            "cape_jkg": nws_data['cape'],
            "shear_mph": nws_data['shear'],
            "source": "NWS API"
        }
    
    # Final fallback to Open-Meteo
    forecast = get_forecast(lat, lon)
    st.error("⚠️ Using Open-Meteo forecast (least accurate)")
    return {
        "cape_jkg": forecast[0]["cape"],
        "shear_mph": forecast[0]["windgusts_10m"],  # Approximate
        "source": "Open-Meteo"
    }

# --- Visualization Functions ---
def plot_weather_trend(times: List[str], values: List[float], 
                      title: str, color: str, ylabel: str):
    """Create a consistent weather trend plot"""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, values, marker="o", color=color, linewidth=2, markersize=8)
    ax.set_ylabel(ylabel, fontweight='bold')
    ax.set_xlabel("Time", fontweight='bold')
    ax.set_title(title, fontweight='bold')
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

def set_background_theme(now: datetime, sunrise: datetime, sunset: datetime):
    """Set dynamic background based on time of day"""
    if now < sunrise - timedelta(minutes=90) or now > sunset + timedelta(minutes=90):
        bg = "#000000"  # Night
    elif sunrise - timedelta(minutes=90) <= now < sunrise - timedelta(minutes=30):
        bg = "#1a1a2e"  # Late night/early dawn
    elif sunrise - timedelta(minutes=30) <= now < sunrise:
        bg = "#2c3e50"  # Dawn
    elif sunrise <= now < sunrise + timedelta(minutes=30):
        bg = "#ff914d"  # Sunrise
    elif sunset - timedelta(minutes=30) <= now < sunset:
        bg = "#ff914d"  # Sunset
    elif sunset <= now < sunset + timedelta(minutes=30):
        bg = "#2c3e50"  # Dusk
    else:
        bg = "#fff8cc"  # Daytime
        
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: {bg};
        transition: background-color 0.5s ease;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- Main Application ---
def main():
    # Get location
    with st.spinner("Detecting location..."):
        lat, lon, label = get_user_location()
    
    st.markdown(f"**Location:** {label}")
    st.map({"lat": [lat], "lon": [lon]})
    
    # Get weather data
    with st.spinner("Fetching weather data..."):
        # Get severe weather metrics
        metrics = get_severe_metrics(lat, lon)
        
        # Get forecast data
        forecast_data = get_forecast(lat, lon)
        if None in forecast_data:
            st.error("Failed to retrieve forecast data. Please try again later.")
            st.stop()
            
        (hourly_forecast, precip_24h, times, cape_vals, cin_vals, 
         full_times, sunrise, sunset, timezone) = forecast_data
        
        now = datetime.fromisoformat(full_times[0]).replace(tzinfo=ZoneInfo(timezone))
        sunrise = sunrise.replace(tzinfo=ZoneInfo(timezone))
        sunset = sunset.replace(tzinfo=ZoneInfo(timezone))
        set_background_theme(now, sunrise, sunset)

    # Display header information
    st.caption(f"**Local Time (Forecast Location):** {now.strftime('%A %I:%M %p')} ({timezone})")
    st.caption(f"**Sunrise:** {sunrise.strftime('%I:%M %p')} | **Sunset:** {sunset.strftime('%I:%M %p')}")
    
    # Severe weather metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "CAPE", 
            f"{metrics['cape_jkg']} J/kg",
            help="Convective Available Potential Energy"
        )
    with col2:
        st.metric(
            "0-6km Shear", 
            f"{metrics['shear_mph']:.1f} mph",
            help="Bulk wind shear (storm organization potential)"
        )
    st.caption(f"Source: {metrics.get('source', 'Unknown')} | Updated: {metrics.get('last_updated', 'N/A')}")
    
    # Real-time shear map
    st.subheader("Real-Time HRRR 0–6 km Bulk Shear Map")
    shear_img_url = "https://www.pivotalweather.com/data/models/hrrr/latest/shear_06km.png"
    st.image(shear_img_url, caption="Bulk Shear (HRRR) from Pivotal Weather", use_column_width=True)
    
    # CAPE Trend
    st.subheader("CAPE Trend (Next 12 Hours)")
    st.pyplot(plot_weather_trend(times, cape_vals, "CAPE Trend", "goldenrod", "CAPE (J/kg)"))
    
    # CIN Trend
    st.subheader("CIN Trend (Next 12 Hours)")
    st.pyplot(plot_weather_trend(times, cin_vals, "CIN Trend", "purple", "CIN (J/kg)"))
    
    # Precipitation summary
    st.subheader(f"24-Hour Precipitation: {precip_24h:.2f} in")
    
    # Hourly forecast blocks
    for hour in hourly_forecast:
        with st.container():
            st.markdown(f"### {hour['time']}")
            
            cols = st.columns(3)
            with cols[0]:
                st.metric("Temperature", f"{hour['temperature']} °F")
                st.metric("Dewpoint", f"{hour['dewpoint']} °F")
                st.metric("CIN", f"{hour['cin']:.0f} J/kg")
                
            with cols[1]:
                st.metric("Wind Speed / Gusts", f"{hour['windSpeed']} / {hour['windGusts']} mph")
                st.metric("Cloud Cover / Humidity", f"{hour['cloudCover']}% / {hour['humidity']}%")
                
            with cols[2]:
                st.metric("Precipitation", f"{hour['precipitation']} in ({hour['precipProbability']}%)")
            
            st.markdown("---")

if __name__ == "__main__":
    main()
