import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import matplotlib.pyplot as plt

st.set_page_config("Severe Weather Dashboard", layout="centered")
st.title("Severe Weather Dashboard (Powered by Tomorrow.io)")

API_KEY = "4q4STtGVpjZXJ2VredMSnQxdo5q5orOM"

@st.cache_data(ttl=900)
def get_tomorrowio_data(lat, lon):
    url = (
        f"https://api.tomorrow.io/v4/weather/forecast"
        f"?location={lat},{lon}"
        f"&timesteps=1h&units=imperial"
        f"&fields=temperature,dewPoint,humidity,windSpeed,windGust,"
        f"precipitationIntensity,cloudCover,cap,cin"
        f"&apikey={API_KEY}"
    )
    r = requests.get(url)
    if r.status_code != 200:
        st.error(f"Tomorrow.io API error: {r.status_code} - {r.text}")
        return None
    return r.json()

@st.cache_data
def geocode_location(query):
    geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={query}&country=US").json()
    if "results" in geo:
        res = geo["results"][0]
        return res["latitude"], res["longitude"], res["name"]
    return 32.9, -97.3, "DFW"

user_input = st.text_input("Enter ZIP Code or City, State", "76247")
lat, lon, label = geocode_location(user_input)
st.markdown(f"**Location:** {label}")
st.map({"lat": [lat], "lon": [lon]})

data = get_tomorrowio_data(lat, lon)
if not data:
    st.stop()

hours = data['timelines']['hourly']
df = pd.DataFrame([{
    "time": datetime.fromisoformat(h["time"]).strftime("%a %I:%M %p"),
    "temp": h["values"].get("temperature"),
    "dew": h["values"].get("dewPoint"),
    "humidity": h["values"].get("humidity"),
    "wind": h["values"].get("windSpeed"),
    "gusts": h["values"].get("windGust"),
    "precip": h["values"].get("precipitationIntensity", 0),
    "clouds": h["values"].get("cloudCover"),
    "cape": h["values"].get("cap", 0),
    "cin": h["values"].get("cin", 0)
} for h in hours[:12]])

def calculate_risk(row):
    score = 0
    if row["cape"] >= 3000: score += 30
    elif row["cape"] >= 2000: score += 20
    elif row["cape"] >= 1000: score += 10
    if row["gusts"] >= 60: score += 25
    elif row["gusts"] >= 45: score += 15
    if row["precip"] >= 1: score += 15
    elif row["precip"] >= 0.3: score += 10
    if row["humidity"] >= 80 and row["dew"] >= 65: score += 10
    elif row["humidity"] >= 60 and row["dew"] >= 60: score += 5
    if row["cin"] <= -100:
        score -= 20
    elif -100 < row["cin"] <= -50:
        score -= 10
    elif row["cin"] >= 0:
        score += 10
    return max(min(score, 100), 0)

df["risk"] = df.apply(calculate_risk, axis=1)

# 🌅 Local time from first forecast entry
timezone = "America/Chicago"  # fallback timezone
local_time = datetime.fromisoformat(hours[0]["time"]).replace(tzinfo=ZoneInfo(timezone))
st.caption(f"**Local Forecast Time:** {local_time.strftime('%A %I:%M %p')} ({timezone})")

# 📊 Trend Charts
st.subheader("CAPE & CIN Trend")
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(df["time"], df["cape"], label="CAPE", color="orange", marker="o")
ax.set_ylabel("CAPE (J/kg)", color="orange")
ax.tick_params(axis='y', labelcolor="orange")
ax2 = ax.twinx()
ax2.plot(df["time"], df["cin"], label="CIN", color="purple", linestyle="--", marker="o")
ax2.set_ylabel("CIN (J/kg)", color="purple")
ax2.tick_params(axis='y', labelcolor="purple")
fig.autofmt_xdate()
st.pyplot(fig)

# 📊 Forecast Display
st.subheader("Severe Weather Risk - Next 12 Hours")
for _, row in df.iterrows():
    st.markdown(f"### {row['time']}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Temp", f"{row['temp']} °F")
        st.metric("Dew Point", f"{row['dew']} °F")
        st.metric("CIN", f"{row['cin']:.0f} J/kg")
    with col2:
        st.metric("Wind", f"{row['wind']} mph")
        st.metric("Gusts", f"{row['gusts']} mph")
        st.metric("Humidity", f"{row['humidity']}%")
    with col3:
        st.metric("Precip", f"{row['precip']:.2f} in/hr")
        st.metric("CAPE", f"{row['cape']:.0f} J/kg")
        st.metric("Risk Score", f"{row['risk']}/100")
        st.progress(row["risk"] / 100)
    st.markdown("---")
