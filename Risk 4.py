import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from time import time

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
        f"precipitationIntensity,cloudCover,cap,cin,windSpeed1000hpa,windSpeed500hpa,stormRelativeHelicity"
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
st.map({"lat": [lat], "lon": [lon]}, zoom=9, use_container_width=True)

# 🚨 NWS Alerts Overlay
alerts_url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
alerts = requests.get(alerts_url).json()
if "features" in alerts and alerts["features"]:
    for alert in alerts["features"]:
        event = alert["properties"].get("event", "Alert")
        area = alert["properties"].get("areaDesc", "")
        headline = alert["properties"].get("headline", "")
        st.warning(f"{event} for {area}: {headline}")

# ⏱ Radar Refresh Control
if 'radar_last_refresh' not in st.session_state:
    st.session_state.radar_last_refresh = time()

if time() - st.session_state.radar_last_refresh > 60:
    st.session_state.radar_last_refresh = time()
    st.experimental_rerun()

# 🌧 MRMS Radar Image (via NOAA)
radar_url = f"https://radar.weather.gov/ridge/standard/KFWS_loop.gif?{int(time())}"
st.image(radar_url, caption="NWS Radar (KFWS)", use_container_width=True)

# Forecast Data
forecast = get_tomorrowio_data(lat, lon)
if not forecast:
    st.stop()

hours = forecast['timelines']['hourly']
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
    "cin": h["values"].get("cin", 0),
    "shear": abs(h["values"].get("windSpeed500hpa", 0) - h["values"].get("windSpeed1000hpa", 0)),
    "srh": h["values"].get("stormRelativeHelicity", 0)
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
    if row["shear"] >= 40:
        score += 10
    elif row["shear"] >= 30:
        score += 5
    if row["srh"] >= 150:
        score += 10
    elif row["srh"] >= 100:
        score += 5
    return max(min(score, 100), 0)

df["risk"] = df.apply(calculate_risk, axis=1)

# 🔥 Current Risk Bar
current_risk = df.iloc[0]["risk"]
risk_color = '#ff4d4d' if current_risk >= 70 else '#ffaa00' if current_risk >= 40 else '#2ecc71'
st.markdown(f"**Current Severe Weather Risk:** {current_risk}/100")
st.markdown(f"<div style='height: 20px; width: {current_risk}%; background-color: {risk_color}; border-radius: 4px; transition: width 0.8s ease-in-out, background-color 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# 🌪️🌡️ CAPE / Shear / SRH Display
st.markdown("## Current Severe Indices")
row = df.iloc[0]

cols = st.columns(3)

# CAPE
with cols[0]:
    st.markdown(f"**CAPE**")
    st.markdown(f"<div style='font-size: 28px'>{row['cape']:.0f} J/kg</div>", unsafe_allow_html=True)
    cape_val = row["cape"]
    cape_color = "#ff4d4d" if cape_val >= 3000 else "#ffaa00" if cape_val >= 1500 else "#2ecc71"
    cape_emoji = "🌪️" if cape_val >= 3000 else "⚠️" if cape_val >= 1500 else "✅"
    cape_width = max(min(cape_val / 40, 100), 5)
    st.markdown(f"{cape_emoji} <div style='height: 12px; width: {cape_width}%; background-color: {cape_color}; border-radius: 6px; transition: width 0.8s ease-in-out, background-color 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# Shear
with cols[1]:
    st.markdown(f"**Shear (ΔSpeed)**")
    st.markdown(f"<div style='font-size: 28px'>{row['shear']:.1f} mph</div>", unsafe_allow_html=True)
    shear_val = row["shear"]
    shear_color = "#ff4d4d" if shear_val >= 40 else "#ffaa00" if shear_val >= 30 else "#2ecc71"
    shear_emoji = "💨" if shear_val >= 40 else "⚠️" if shear_val >= 30 else "✅"
    shear_width = max(min(shear_val, 100), 5)
    st.markdown(f"{shear_emoji} <div style='height: 12px; width: {shear_width}%; background-color: {shear_color}; border-radius: 6px; transition: width 0.8s ease-in-out, background-color 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# SRH
with cols[2]:
    st.markdown(f"**SRH**")
    st.markdown(f"<div style='font-size: 28px'>{row['srh']:.0f} m²/s²</div>", unsafe_allow_html=True)
    srh_val = row["srh"]
    srh_color = "#ff4d4d" if srh_val >= 150 else "#ffaa00" if srh_val >= 100 else "#2ecc71"
    srh_emoji = "🌀" if srh_val >= 150 else "⚠️" if srh_val >= 100 else "✅"
    srh_width = max(min(srh_val / 2, 100), 5)
    st.markdown(f"{srh_emoji} <div style='height: 12px; width: {srh_width}%; background-color: {srh_color}; border-radius: 6px; transition: width 0.8s ease-in-out, background-color 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# ℹ️ Legend
with st.expander("ℹ️ Emoji Legend for Severity Bars"):
    st.markdown("""
    - **🌪️** CAPE: Extreme instability (≥ 3000 J/kg)
    - **💨** Shear: High wind shear (≥ 40 mph)
    - **🌀** SRH: Strong storm-relative helicity (≥ 150 m²/s²)
    - **⚠️** Moderate values
    - **✅** Benign conditions
    """)
