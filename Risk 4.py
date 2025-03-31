import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from geopy.distance import geodesic
from io import StringIO
import matplotlib.pyplot as plt
from typing import Optional, Tuple, Dict, List

# Configuration
API_TIMEOUT = 10  # seconds
CACHE_TTL = 1800  # 30 minutes in seconds
DEFAULT_LOCATION = {"lat": 32.9, "lon": -97.3, "label": "DFW Metroplex"}

# Constants
WEATHER_STATIONS = {
    "KOUN": {"lat": 35.23, "lon": -97.46},
    "KFWD": {"lat": 32.83, "lon": -97.30},
    "KAMA": {"lat": 35.22, "lon": -101.72},
    "KLZK": {"lat": 34.83, "lon": -92.26},
    "KSHV": {"lat": 32.45, "lon": -93.83}
}

# Setup Streamlit
st.set_page_config("Severe Weather Dashboard", layout="centered")
st.title("Severe Weather Dashboard")

# --- Helper Functions ---
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
    # Try browser geolocation first
    browser_coords = get_browser_location()
    if browser_coords:
        lat, lon = browser_coords
        return lat, lon, "Detected Location (via Browser)"
    
    # Fall back to user input
    user_input = st.text_input("Enter ZIP Code or City, State", "76247")
    if user_input.isnumeric():
        return get_coordinates_from_zip(user_input)
    else:
        return get_coordinates_from_city(user_input)

def find_nearest_station(lat: float, lon: float) -> str:
    """Find nearest weather station from coordinates"""
    return min(WEATHER_STATIONS, 
              key=lambda s: geodesic((lat, lon), 
                                   (WEATHER_STATIONS[s]['lat'], 
                                    WEATHER_STATIONS[s]['lon'])).miles)

@st.cache_data(ttl=CACHE_TTL)
def get_rap_cape(station: str) -> Optional[float]:
    """Get RAP sounding CAPE data from Iowa State Mesonet"""
    try:
        now = datetime.utcnow()
        url = (
            "https://mesonet.agron.iastate.edu/cgi-bin/request/raob.py?"
            f"station={station}&data=cape&year1={now.year}&month1={now.month}&day1={now.day}"
            f"&year2={now.year}&month2={now.month}&day2={now.day}&format=comma&latlon=no&direct=yes"
        )
        r = requests.get(url, timeout=API_TIMEOUT)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        return df["cape"].dropna().iloc[-1] if "cape" in df.columns and not df["cape"].dropna().empty else None
    except Exception as e:
        st.error(f"Failed to get RAP CAPE data: {str(e)}")
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

def calculate_risk_score(cape: float, forecast: Dict) -> int:
    """Calculate severe weather risk score (0-100)"""
    score = 0
    
    # CAPE contribution
    if cape >= 3000: score += 30
    elif cape >= 2000: score += 20
    elif cape >= 1000: score += 10
    
    # Wind contribution
    if forecast["windGusts"] >= 60: score += 25
    elif forecast["windGusts"] >= 45: score += 15
    
    # Precipitation contribution
    if forecast["precipitation"] >= 1: score += 15
    elif forecast["precipitation"] >= 0.3: score += 10
    
    # Moisture contribution
    if forecast["humidity"] >= 80 and forecast["dewpoint"] >= 65: score += 10
    elif forecast["humidity"] >= 60 and forecast["dewpoint"] >= 60: score += 5
    
    # CIN (inhibition) adjustment
    cin = forecast["cin"]
    if cin <= -100:
        score -= 20  # Strong cap suppresses storms
    elif -100 < cin <= -50:
        score -= 10  # Moderate cap may break
    elif cin >= 0:
        score += 10  # No cap favors storms
        
    return max(min(score, 100), 0)

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

# --- Main Application ---
def main():
    # Get location
    with st.spinner("Detecting location..."):
        lat, lon, label = get_user_location()
    
    st.markdown(f"**Location:** {label}")
    st.map({"lat": [lat], "lon": [lon]})
    
    # Get weather data
    with st.spinner("Fetching weather data..."):
        station = find_nearest_station(lat, lon)
        cape = get_rap_cape(station)
        forecast_data = get_forecast(lat, lon)
        
        if None in forecast_data:
            st.error("Failed to retrieve forecast data. Please try again later.")
            st.stop()
            
        (forecast_data, precip_24h, times, cape_vals, cin_vals, 
         full_times, sunrise, sunset, timezone) = forecast_data
        
        now = datetime.fromisoformat(full_times[0]).replace(tzinfo=ZoneInfo(timezone))
        sunrise = sunrise.replace(tzinfo=ZoneInfo(timezone))
        sunset = sunset.replace(tzinfo=ZoneInfo(timezone))
        set_background_theme(now, sunrise, sunset)
        
        # Use forecast CAPE if RAP data isn't available
        cape = cape or forecast_data[0]["cape"]
        cape_source = f"RAP Sounding (Station: {station})" if cape else "Open-Meteo Forecast"
        cape_time = datetime.utcnow().strftime("%a %I:%M %p UTC") if cape else now.strftime("%a %I:%M %p")

    # Display header information
    st.caption(f"**Local Time (Forecast Location):** {now.strftime('%A %I:%M %p')} ({timezone})")
    st.caption(f"**Sunrise:** {sunrise.strftime('%I:%M %p')} | **Sunset:** {sunset.strftime('%I:%M %p')}")
    
    # CAPE display
    st.subheader(f"CAPE: {cape:.0f} J/kg")
    st.caption(f"Source: {cape_source}")
    st.caption(f"Updated: {cape_time}")
    
    # Real-time shear map
    st.subheader("Real-Time HRRR 0–6 km Bulk Shear Map")
    shear_img_url = "https://www.pivotalweather.com/maps/models/hrrr/20240330/1800/shear-bulk06h/hrrr_CONUS_202403301800_bulk06h_f000.png"
    st.image(shear_img_url, caption="Bulk Shear (HRRR) from Pivotal Weather", use_column_width=True)
    
    # CAPE Trend Plot
    st.subheader("CAPE Trend (Next 12 Hours)")
    st.pyplot(plot_weather_trend(times, cape_vals, "CAPE Trend", "goldenrod", "CAPE (J/kg)"))
    
    # CIN Trend Plot
    st.subheader("CIN Trend (Next 12 Hours)")
    st.pyplot(plot_weather_trend(times, cin_vals, "CIN Trend", "purple", "CIN (J/kg)"))
    
    # Precipitation summary
    st.subheader(f"24-Hour Precipitation: {precip_24h:.2f} in")
    
    # Hourly forecast blocks
    for hour in forecast_data:
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
                risk = calculate_risk_score(cape, hour)
                st.metric("Risk Score", f"{risk}/100")
                st.progress(risk / 100)
            
            # CIN warning/status
            cin_val = hour["cin"]
            if cin_val <= -100:
                st.error("Strong Cap Present: Storms suppressed unless lifted.")
            elif -100 < cin_val <= -50:
                st.warning("Moderate Cap: May break with heating or lift.")
            elif cin_val > -50:
                st.success("Weak or No Cap: Storms more likely.")
            
            st.markdown("---")

if __name__ == "__main__":
    main()
