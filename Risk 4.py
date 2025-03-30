import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
from geopy.distance import geodesic
from io import StringIO
import matplotlib.pyplot as plt

# Sounding stations
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
        f"cloudcover,dewpoint_2m,relative_humidity_2m,cape,convective_inhibition"
        f"&daily=precipitation_sum,sunrise,sunset&past_days=1&forecast_days=1"
        f"&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch&timezone=auto"
    )
    res = requests.get(url).json()
    hourly = res["hourly"]
    central = pytz.timezone("US/Central")
    now = datetime.now(central)

    data = []
    for i, time in enumerate(hourly["time"]):
        dt = datetime.fromisoformat(time).astimezone(central)
        if dt > now and len(data) < 12:
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

    times = [datetime.fromisoformat(t).astimezone(central).strftime("%I %p") for t in hourly["time"][:12]]
    cape_vals = hourly["cape"][:12]
    cin_vals = hourly["convective_inhibition"][:12]

    daily = res["daily"]
    precip_24h = daily["precipitation_sum"][0]
    sunrise = datetime.fromisoformat(daily["sunrise"][0]).astimezone(central)
    sunset = datetime.fromisoformat(daily["sunset"][0]).astimezone(central)

    return data, precip_24h, times, cape_vals, cin_vals, hourly["time"], sunrise, sunset

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
    cin = forecast["cin"]
    if cin <= -100:
        score -= 20
    elif -100 < cin <= -50:
        score -= 10
    elif cin >= 0:
        score += 10
    return max(min(score, 100), 0)

def set_background_theme(now, sunrise, sunset):
    if now < sunrise - timedelta(minutes=90) or now > sunset + timedelta(minutes=90):
        bg = "#000000"  # Night
    elif sunrise - timedelta(minutes=90) <= now < sunrise - timedelta(minutes=30):
        bg = "#1a1a2e"  # Astronomical Twilight
    elif sunrise - timedelta(minutes=30) <= now < sunrise:
        bg = "#2c3e50"  # Nautical Twilight
    elif sunrise <= now < sunrise + timedelta(minutes=30):
        bg = "#ff914d"  # Sunrise
    elif sunset - timedelta(minutes=30) <= now < sunset:
        bg = "#ff914d"  # Sunset
    elif sunset <= now < sunset + timedelta(minutes=30):
        bg = "#2c3e50"  # Civil Twilight
    else:
        bg = "#fff8cc"  # Full Daylight

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {bg};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

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
    forecast_data, precip_24h, times, cape_vals, cin_vals, full_times, sunrise, sunset = get_forecast(lat, lon)

    now = datetime.now(pytz.timezone("US/Central"))
    set_background_theme(now, sunrise, sunset)
    st.caption(f"**Local Time:** {now.strftime('%A %I:%M %p CT')}")
    st.caption(f"**Sunrise:** {sunrise.strftime('%I:%M %p')} | **Sunset:** {sunset.strftime('%I:%M %p')}")

    cape_source = f"Real-Time RAP Sounding (Station: {station})" if cape else "Model Forecast CAPE (Open-Meteo Fallback)"
    cape_time = datetime.utcnow().strftime("%a %I:%M %p UTC") if cape else datetime.fromisoformat(full_times[0]).astimezone(pytz.timezone("US/Central")).strftime("%a %I:%M %p CT")
    cape = cape or forecast_data[0]["cape"]

    st.subheader(f"CAPE: {cape:.0f} J/kg")
    st.caption(f"Source: {cape_source}")
    st.caption(f"Updated: {cape_time}")

    # CAPE Trend
    st.subheader("CAPE Trend (Next 12 Hours)")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, cape_vals, marker="o", color="goldenrod")
    ax.set_ylabel("CAPE (J/kg)")
    ax.set_xlabel("Time (CT)")
    ax.set_title("Forecasted CAPE")
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig)

    # CIN Trend
    st.subheader("CIN Trend (Next 12 Hours)")
    fig2, ax2 = plt.subplots(figsize=(10, 4))
    ax2.plot(times, cin_vals, marker="o", color="purple")
    ax2.set_ylabel("CIN (J/kg)")
    ax2.set_xlabel("Time (CT)")
    ax2.set_title("Forecasted CIN")
    ax2.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig2)

    # Forecast Blocks
    st.subheader(f"24-Hour Precipitation: {precip_24h:.2f} in")
    for hour in forecast_data:
        with st.container():
            st.markdown(f"### {hour['time']}")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Temp", f"{hour['temperature']} °F")
                st.metric("Dewpoint", f"{hour['dewpoint']} °F")
                st.metric("CIN", f"{hour['cin']:.0f} J/kg")

            with col2:
                st.metric("Wind / Gusts", f"{hour['windSpeed']} / {hour['windGusts']} mph")
                st.metric("Cloud / Humidity", f"{hour['cloudCover']}% / {hour['humidity']}%")

            with col3:
                st.metric("Precip", f"{hour['precipitation']} in ({hour['precipProbability']}%)")
                risk = calculate_risk(cape, hour)
                st.metric("Risk Score", f"{risk}/100")
                st.progress(risk / 100)

            # CIN messages
            cin_val = hour["cin"]
            if cin_val <= -100:
                st.error("Strong Cap Present: Storms suppressed unless lifted.")
            elif -100 < cin_val <= -50:
                st.warning("Moderate Cap: May break with heating or lift.")
            elif cin_val > -50:
                st.success("Weak or No Cap: Storms more likely.")

            st.markdown("---")
            st.caption(f"Sunrise Raw: {daily['sunrise'][0]}")
st.caption(f"Sunset Raw: {daily['sunset'][0]}")
            