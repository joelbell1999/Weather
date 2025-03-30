import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import pytz
from geopy.distance import geodesic
from io import StringIO

# Sounding stations with locations
stations = {
    "KOUN": {"lat": 35.23, "lon": -97.46},  # Norman, OK
    "KFWD": {"lat": 32.83, "lon": -97.30},  # Fort Worth, TX
    "KAMA": {"lat": 35.22, "lon": -101.72},  # Amarillo, TX
    "KLZK": {"lat": 34.83, "lon": -92.26},   # Little Rock, AR
    "KSHV": {"lat": 32.45, "lon": -93.83}    # Shreveport, LA
}

# Find nearest station to lat/lon
def find_nearest_station(lat, lon):
    min_dist = float("inf")
    nearest = None
    for station, loc in stations.items():
        dist = geodesic((lat, lon), (loc["lat"], loc["lon"])).miles
        if dist < min_dist:
            min_dist = dist
            nearest = station
    return nearest

# Get CAPE from IEM sounding
def get_rap_cape(station):
    now = datetime.utcnow()
    url = (
        "https://mesonet.agron.iastate.edu/cgi-bin/request/raob.py?"
        f"station={station}&data=cape&year1={now.year}&month1={now.month}&day1={now.day}"
        f"&year2={now.year}&month2={now.month}&day2={now.day}&format=comma&latlon=no&direct=yes"
    )
    r = requests.get(url)
    if r.status_code != 200:
        return None
    df = pd.read_csv(StringIO(r.text))
    if "cape" in df.columns and not df["cape"].dropna().empty:
        return df["cape"].dropna().iloc[-1]
    return None

# ZIP to lat/lon via Zippopotam.us
def zip_to_latlon(zip_code):
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}")
        data = r.json()
        city = data["places"][0]["place name"]
        state = data["places"][0]["state abbreviation"]
        lat = float(data["places"][0]["latitude"])
        lon = float(data["places"][0]["longitude"])
        return lat, lon, f"{city}, {state}"
    except:
        return None, None, None

# City to lat/lon via Open-Meteo geocoder
def city_to_latlon(city_name):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&country=US"
    res = requests.get(url).json()
    if "results" in res and len(res["results"]) > 0:
        r = res["results"][0]
        return r["latitude"], r["longitude"], r.get("name", "Unknown")
    return None, None, None

# Streamlit UI
st.set_page_config("Real-Time CAPE from RAP Soundings", layout="centered")
st.title("Real-Time SBCAPE from RAP Soundings (via IEM)")

user_input = st.text_input("Enter ZIP Code or City, State", "76247")

# Get lat/lon from input
if user_input:
    if user_input.isnumeric() and len(user_input) == 5:
        lat, lon, location_label = zip_to_latlon(user_input)
    else:
        lat, lon, location_label = city_to_latlon(user_input)

    if not lat or not lon:
        st.warning("Could not resolve location. Defaulting to DFW.")
        lat, lon, location_label = 32.9, -97.3, "DFW Metroplex"

    st.markdown(f"**Location:** {location_label}")
    st.map({"lat": [lat], "lon": [lon]})

    nearest_station = find_nearest_station(lat, lon)
    st.markdown(f"**Nearest RAP Sounding Station:** `{nearest_station}`")

    cape = get_rap_cape(nearest_station)

    if cape is not None:
        st.success(f"Latest SBCAPE at {nearest_station}: **{cape:.0f} J/kg**")
        st.progress(min(cape / 4000, 1.0))
    else:
        st.error("No CAPE data available from the nearest sounding.")