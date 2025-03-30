import requests
import streamlit as st

st.set_page_config(page_title="DFW Weather Risk", layout="centered")

# Get current location from IP
def get_current_location():
    ipinfo_response = requests.get('https://ipinfo.io/json')
    if ipinfo_response.status_code != 200:
        return None
    location_data = ipinfo_response.json()
    lat, lon = location_data['loc'].split(',')
    return float(lat), float(lon)

# Get precipitation over the last 24 hours
def get_precipitation_past_24hrs(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily=precipitation_sum&past_days=1&forecast_days=0"
        f"&precipitation_unit=inch&timezone=auto"
    )
    response = requests.get(url)
    if response.status_code == 200:
        daily_data = response.json().get('daily', {})
        precip_sums = daily_data.get('precipitation_sum', [0])
        return precip_sums[-1]
    return 0

# Get current weather data
def get_weather_data():
    location = get_current_location()
    if not location:
        return [], 0

    lat, lon = location
    precip_last_24hrs = get_precipitation_past_24hrs(lat, lon)
    weather_data = []

    forecast_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,windspeed_10m,windgusts_10m,weathercode,precipitation,precipitation_probability,cloudcover,dewpoint_2m,cape,relative_humidity_2m,surface_pressure"
        f"&forecast_days=1&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch&timezone=auto"
    )

    response = requests.get(forecast_url)
    if response.status_code == 200:
        data = response.json().get('hourly', {})
        for i in range(3):
            weather_data.append({
                'time': data['time'][i],
                'temperature': data['temperature_2m'][i],
                'windSpeed': data['windspeed_10m'][i],
                'windGusts': data['windgusts_10m'][i],
                'weatherCode': data['weathercode'][i],
                'precipitation': data['precipitation'][i],
                'precipProbability': data['precipitation_probability'][i],
                'cloudCover': data['cloudcover'][i],
                'dewpoint': data['dewpoint_2m'][i],
                'cape': data['cape'][i],
                'humidity': data['relative_humidity_2m'][i],
                'pressure': data['surface_pressure'][i]
            })

    return weather_data, precip_last_24hrs

# Calculate risk score
def calculate_severe_risk(period):
    risk = 0
    if period['windSpeed'] >= 58 or period['windGusts'] >= 60:
        risk += 30
    elif period['windSpeed'] >= 40 or period['windGusts'] >= 50:
        risk += 20
    elif period['windSpeed'] >= 30 or period['windGusts'] >= 40:
        risk += 10

    if period['cape'] >= 3500:
        risk += 30
    elif period['cape'] >= 2500:
        risk += 20
    elif period['cape'] >= 1500:
        risk += 10

    if period['precipProbability'] >= 70:
        risk += 20
    elif period['precipProbability'] >= 40:
        risk += 10

    if period['cloudCover'] >= 85 and period['humidity'] >= 75:
        risk += 10

    if period['dewpoint'] >= 70:
        risk += 10
    elif period['dewpoint'] >= 65:
        risk += 5

    return min(risk, 100)

# Streamlit UI
st.title("DFW Severe Weather Risk")

weather_data, precip_last_24hrs = get_weather_data()

st.subheader(f"Precipitation in Last 24 Hours: {precip_last_24hrs} inches")

if not weather_data:
    st.error("Could not retrieve weather data.")
else:
    for period in weather_data:
        risk = calculate_severe_risk(period)
        st.write(f"### Forecast for {period['time']}")
        st.metric("Temperature", f"{period['temperature']} °F")
        st.metric("Wind / Gusts", f"{period['windSpeed']} / {period['windGusts']} mph")
        st.metric("Precipitation", f"{period['precipitation']} in ({period['precipProbability']}%)")
        st.metric("Cloud / Humidity", f"{period['cloudCover']}% / {period['humidity']}%")
        st.metric("Dewpoint", f"{period['dewpoint']} °F")
        st.metric("CAPE", f"{period['cape']} J/kg")
        st.progress(risk / 100)
        st.write(f"**Severe Risk Factor:** {risk}/100")
