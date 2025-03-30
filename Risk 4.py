import streamlit as st
import requests
from datetime import datetime
import pytz

# --- Convert ZIP to lat/lon using Open-Meteo Geocoding API ---
def get_coordinates(zip_code):
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?postal_code={zip_code}&country=US"
    res = requests.get(geo_url)
    data = res.json()
    if "results" in data:
        result = data["results"][0]
        return result["latitude"], result["longitude"], result["name"]
    return None, None, None

# --- Fetch weather data from Open-Meteo API ---
def get_weather_data(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,windspeed_10m,windgusts_10m,precipitation,precipitation_probability,"
        f"cloudcover,dewpoint_2m,cape,relative_humidity_2m,surface_pressure,weathercode"
        f"&daily=precipitation_sum&past_days=1&forecast_days=1"
        f"&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch&timezone=auto"
    )

    response = requests.get(url).json()
    hourly = response["hourly"]
    times = hourly["time"]
    central = pytz.timezone("US/Central")
    now = datetime.now(central)

    weather_data = []
    for i, time_str in enumerate(times):
        dt = datetime.fromisoformat(time_str).astimezone(central)
        if dt > now and len(weather_data) < 3:
            weather_data.append({
                "time": dt.strftime("%a %I:%M %p"),
                "temperature": hourly["temperature_2m"][i],
                "windSpeed": hourly["windspeed_10m"][i],
                "windGusts": hourly["windgusts_10m"][i],
                "precipitation": hourly["precipitation"][i],
                "precipProbability": hourly["precipitation_probability"][i],
                "cloudCover": hourly["cloudcover"][i],
                "dewpoint": hourly["dewpoint_2m"][i],
                "cape": hourly["cape"][i],
                "humidity": hourly["relative_humidity_2m"][i]
            })

    precip_last_24hrs = response.get("daily", {}).get("precipitation_sum", [0])
    precip_24h = precip_last_24hrs[0] if precip_last_24hrs else 0
    return weather_data, precip_24h

# --- Severe risk calculation based on DFW thresholds ---
def calculate_severe_risk(data):
    score = 0
    if data["cape"] >= 3000: score += 30
    elif data["cape"] >= 2000: score += 20
    elif data["cape"] >= 1000: score += 10

    if data["windGusts"] >= 60: score += 25
    elif data["windGusts"] >= 45: score += 15

    if data["precipitation"] >= 1: score += 15
    elif data["precipitation"] >= 0.3: score += 10

    if data["humidity"] >= 80 and data["dewpoint"] >= 65: score += 10
    elif data["humidity"] >= 60 and data["dewpoint"] >= 60: score += 5

    return min(score, 100)

# --- Streamlit UI ---
st.set_page_config("Severe Weather Risk", layout="centered")
st.title("DFW Severe Weather Risk Forecast")

zip_code = st.text_input("Enter ZIP Code", "76247")

if zip_code:
    lat, lon, city = get_coordinates(zip_code)
    if lat and lon:
        st.markdown(f"**Location:** {city} ({zip_code})")
        st.map({"lat": [lat], "lon": [lon]})
        weather_data, precip_24h = get_weather_data(lat, lon)

        st.subheader(f"24-Hour Precipitation: {precip_24h:.2f} inches")

        for period in weather_data:
            risk = calculate_severe_risk(period)
            st.markdown(f"### {period['time']}")
            st.metric("Temperature", f"{period['temperature']} °F")
            st.metric("Wind / Gusts", f"{period['windSpeed']} / {period['windGusts']} mph")
            st.metric("Precipitation", f"{period['precipitation']} in ({period['precipProbability']}%)")
            st.metric("Cloud / Humidity", f"{period['cloudCover']}% / {period['humidity']}%")
            st.metric("Dewpoint", f"{period['dewpoint']} °F")
            st.metric("CAPE", f"{period['cape']} J/kg")
            st.progress(risk / 100)
            st.write(f"**Severe Risk Score:** `{risk}/100`")
    else:
        st.error("Could not find location for that ZIP code.")
