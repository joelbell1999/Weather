import streamlit as st
import requests
from datetime import datetime
import pytz

# Convert ZIP to city/state using Zippopotam.us
def zip_to_city(zip_code):
    try:
        res = requests.get(f"https://api.zippopotam.us/us/{zip_code}")
        data = res.json()
        city = data["places"][0]["place name"]
        state = data["places"][0]["state abbreviation"]
        return f"{city}, {state}"
    except:
        return None

# Get lat/lon from Open-Meteo using city name
def get_coordinates(location_name):
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location_name}&country=US"
    res = requests.get(geo_url)
    data = res.json()
    if "results" in data and len(data["results"]) > 0:
        result = data["results"][0]
        return result["latitude"], result["longitude"], result.get("name", "Unknown")
    return None, None, None

# Get weather data from Open-Meteo
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
    precip_24h = precip_last_24hrs[0] if precip_last
