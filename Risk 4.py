import streamlit as st
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pandas as pd
import requests

# Constants
MAP_URL = "https://www.pivotalweather.com/maps/models/hrrr/20240330/1800/shear-bulk06h/hrrr_CONUS_202403301800_bulk06h_f000.png"

def find_nearest_station(lat, lon):
    # Implement your own logic to find the nearest station
    # For demonstration purposes, let's assume we have a database of stations with their latitudes and longitudes
    station_database = [
        {"name": "Station 1", "lat": 37.7749, "lon": -122.4194},
        {"name": "Station 2", "lat": 34.0522, "lon": -118.2437},
        # Add more stations here...
    ]

    min_distance = float("inf")
    nearest_station = None

    for station in station_database:
        distance = calculate_distance(lat, lon, station["lat"], station["lon"])
        if distance < min_distance:
            min_distance = distance
            nearest_station = station["name"]

    return nearest_station

def calculate_rap_cape_data(station_name):
    # Simulate retrieving RAP cape data from a database or API (replace with actual implementation)
    rap_cape_database = {
        "Station 1": {"cape": 100, "time": datetime.now()},
        "Station 2": {"cape": 50, "time": datetime.now() - timedelta(hours=3)},
        # Add more stations here...
    }

    if station_name in rap_cape_database:
        return rap_cape_database[station_name]
    else:
        return None

def calculate_risk(cape, hour):
    # Implement your own logic to calculate risk score (replace with actual implementation)
    # For demonstration purposes, let's assume a simple formula
    if cape > 100:
        return 50
    elif -100 < cape <= 100:
        return 25
    else:
        return -75

def calculate_distance(lat1, lon1, lat2, lon2):
    import math

    R = 6371.0 # Radius of the Earth in kilometers

    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)

    a = (math.sin(dlat/2) * math.cos(math.radians(lat1)))
            + (math.sin(dlon/2) * math.cos(math.radians(lat1))
               * math.cos(math.radians(lat2)))

    c = 2 * math.atan2(a, math.sqrt((math.pow(a, 2))+(
                math.pow(math.sin(dlat), 2)
                + math.pow(math.sin(dlon), 2))*math.cos(math.radians(lat1))))

    return R*c

# Main application
st.title("Weather Application")
st.write("This is a weather application that displays the current forecast and real-time shear map.")

station = find_nearest_station(st.session_state.lat, st.session_state.lon)

if station:
    rap_cape_data = calculate_rap_cape_data(station)
    if rap_cape_data:
        cape_source = "RAP Sounding"
        cape_time = datetime.now().strftime("%a %I:%M %p UTC")
        risk_score = calculate_risk(rap_cape_data["cape"], 0)

        st.subheader(f"CAPE: {rap_cape_data['cape']} J/kg")
        st.caption(f"Source: {cape_source}")
        st.caption(f"Updated: {cape_time}")

        # Real-time shear map
        st.subheader("Real-Time HRRR 0–6 km Bulk Shear Map")
        img = st.image(MAP_URL, caption="Bulk Shear (HRRR) from Pivotal Weather")

else:
    st.error("No nearest station found.")

# Simulated forecast data
forecast_data = pd.DataFrame({
    "time": [datetime.now()],
    "temperature": ["Temperature"],
    "dewpoint": ["Dew point"],
    "wind_speed": ["Wind speed"],
    "cloud_cover": ["Cloud cover (%)"],
    "humidity": ["Humidity (%)"],
})

col1, col2 = st.columns(2)
with col1:
    fig, ax = plt.subplots()
    ax.plot([0], [50])
    ax.set_title("Simulated Forecast")
ax.grid(True)
plt.tight_layout()

with col2:
    risk_score = 100
    if -75 <= risk_score <= 25:
        st.success(f"Risk Score: {risk_score}")
