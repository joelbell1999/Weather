import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import pytz
from geopy.distance import geodesic
from io import StringIO
import matplotlib.pyplot as plt

stations = {
    "KOUN": {"lat": 35.23, "lon": -97.46},
    "KFWD": {"lat": 32.83, "lon": -97.30},
    "KAMA": {"lat": 35.22, "lon": -101.72},
    "KLZK": {"lat": 34.83, "lon": -92.26},
    "KSHV": {"lat": 32.45, "lon": -93.83}
}

def find_nearest_station(lat, lon):
    return min(stations, key=lambda s: geodesic((lat, lon), (stations[s]['lat'], stations[s]['lon'])).miles)

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
    return df["cape"].dropna().iloc[-1] if "cape" in df.columns and not df["cape"].dropna().empty else None

def zip_to_latlon(zip_code):
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}")
        data = r.json()
        place = data["places"][0]
        return float(place["latitude"]), float(place["longitude"]), f"{place['place name']}, {place['state abbreviation']}"
    except:
        return None, None, None

def city_to_latlon(city):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&country=US"
    r = requests.get(url).json()
    if "results" in r and r["results"]:
        res = r["results"][0]
        return res["latitude"], res["longitude"], res["name"]
    return None, None, None

def get_forecast(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,windspeed_10m,windgusts_10m,precipitation,precipitation_probability,"
        f"cloudcover,dewpoint_2m,relative_humidity_2m,cape&daily=precipitation_sum&past_days=1&forecast_days=1"
        f"&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch&timezone=auto"
    )
    res = requests.get(url).json()
    hourly = res["hourly"]
    central = pytz.timezone("US/Central")
    now = datetime.now(central)

    data = []
    for i, time in enumerate(hourly["time"]):
        dt = datetime.fromisoformat(time).astimezone(central)
        if dt > now and len(data) < 3:
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
                "cape": hourly["cape"][i]
            })

    cape_times = []
    cape_values = []
    for i, time in enumerate(hourly["time"][:12]):
        dt = datetime.fromisoformat(time).astimezone(central)
        cape_times.append(dt.strftime("%I %p"))
        cape_values.append(hourly["cape"][i])

    daily_precip = res.get("daily", {}).get("precipitation_sum", [0])[0]
    return data, daily_precip, cape_times, cape_values, hourly["time"]

def calculate_risk(cape, forecast):
    score = 0
    if cape >= 3000: score += 30
    elif cape >= 2000: score += 20
    elif cape >= 1000: score += 10
    if forecast["windGusts"] >= 60: score += 25
    elif forecast["windGusts"] >= 45: score += 15
    if forecast["precipitation"] >= 1: score += 15
    elif forecast["precipitation"] >= 0.3: score += 10
    if forecast["humidity"] >= 80 and forecast["dewpoint"] >= 65: score += 10
    elif forecast["humidity"] >= 60 and forecast["dewpoint"] >= 60: score += 5
    return min(score, 100)

# --- Streamlit App ---
st.set_page_config("Severe Weather Dashboard", layout="centered")
st.title("Severe Weather Dashboard")
user_input = st.text_input("Enter ZIP Code or City, State", "76247")

if user_input:
    if user_input.isnumeric():
        lat, lon, label = zip_to_latlon(user_input)
    else:
        lat, lon, label = city_to_latlon(user_input)

    if not lat or not lon:
        lat, lon, label = 32.9, -97.3, "DFW Metroplex"
        st.warning("Could not find location. Defaulting to DFW.")

    st.markdown(f"**Location:** {label}")
    st.map({"lat": [lat], "lon": [lon]})

    station = find_nearest_station(lat, lon)
    cape = get_rap_cape(station)
    cape_source = None
    cape_time = None

    forecast_data, precip_24h, cape_times, cape_values, full_times = get_forecast(lat, lon)

    if cape is not None:
        cape_source = f"Real-Time RAP Sounding (Station: {station})"
        cape_time = datetime.utcnow().strftime("%a %I:%M %p UTC")
    else:
        cape = forecast_data[0]["cape"]
        cape_source = "Model Forecast CAPE (Open-Meteo Fallback)"
        model_time = full_times[0]
        cape_time = datetime.fromisoformat(model_time).astimezone(pytz.timezone("US/Central")).strftime("%a %I:%M %p CT")

    st.subheader(f"CAPE: {cape:.0f} J/kg")
    st.caption(f"Source: {cape_source}")
    st.caption(f"Updated: {cape_time}")

    # --- CAPE Trend Chart ---
    st.subheader("CAPE Trend (Next 12 Hours)")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(cape_times, cape_values, marker="o")
    ax.set_ylabel("CAPE (J/kg)")
    ax.set_xlabel("Time (CT)")
    ax.set_title("Forecast CAPE Trend")
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig)

    # --- Forecast + Risk Score ---
    st.subheader(f"24-Hour Precipitation: {precip_24h:.2f} in")
    for hour in forecast_data:
        risk = calculate_risk(cape, hour)
        st.markdown(f"### {hour['time']}")
        st.metric("Temp", f"{hour['temperature']} °F")
        st.metric("Wind / Gusts", f"{hour['windSpeed']} / {hour['windGusts']} mph")
        st.metric("Precip", f"{hour['precipitation']} in ({hour['precipProbability']}%)")
        st.metric("Cloud / Humidity", f"{hour['cloudCover']}% / {hour['humidity']}%")
        st.metric("Dewpoint", f"{hour['dewpoint']} °F")
        st.metric("Risk Score", f"{risk}/100")
        st.progress(risk / 100)