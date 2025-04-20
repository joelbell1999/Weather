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
import folium
from streamlit_folium import st_folium

with st.container():
    m = folium.Map(location=[lat, lon], zoom_start=8, control_scale=True, prefer_canvas=True)
    folium.Marker([lat, lon], tooltip=f"{label}").add_to(m)

    # Add RainViewer radar tile overlay
    folium.raster_layers.TileLayer(
        tiles="https://tilecache.rainviewer.com/v2/radar/nowcast/0/256/{z}/{x}/{y}/1/1_1.png",
        attr="RainViewer",
        name="RainViewer Radar",
        opacity=0.6,
        overlay=True,
        control=True
    ).add_to(m)

    folium.LayerControl().add_to(m)

    # Add SPC surface boundaries
@st.cache_data(ttl=300)
def get_surface_boundaries():
    try:
        return requests.get("https://mesonet.agron.iastate.edu/geojson/surface_fronts.geojson", timeout=5).json()
    except:
        return None

boundary_data = get_surface_boundaries()
if boundary_data and boundary_data.get("features"):
    for feature in boundary_data.get("features", []):
        coords = feature["geometry"]["coordinates"]
        for line in coords:
            f_type = feature.get("properties", {}).get("type", "Boundary")
            color_map = {
                "COLD": "blue",
                "WARM": "red",
                "STATIONARY": "purple",
                "DRYLINE": "orange"
            }
            line_color = color_map.get(f_type.upper(), "gray")
            folium.PolyLine(locations=[(pt[1], pt[0]) for pt in line], color=line_color, weight=3, tooltip=f_type).add_to(m)

st_data = st_folium(m, width=700, height=450, returned_objects=["last_center", "last_bounds", "zoom"])

# Sync map interaction with dashboard display
if st_data and "last_center" in st_data:
    lat = st_data["last_center"][0]
    lon = st_data["last_center"][1]

# 🧭 SPC Outlook Overlay
import geopandas as gpd
from shapely.geometry import shape

from datetime import date, timedelta
import urllib.request

today = date.today().strftime("%Y%m%d")
yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

def shapefile_available(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req)
        return True
    except:
        return False

shapefile_url = f"https://www.spc.noaa.gov/products/outlook/archive/{today[:4]}/day1otlk_cat_{today}_1300.zip"
used_yesterday = False

if not shapefile_available(shapefile_url):
    shapefile_url = f"https://www.spc.noaa.gov/products/outlook/archive/{yesterday[:4]}/day1otlk_cat_{yesterday}_1300.zip"
    used_yesterday = True

import zipfile
from io import BytesIO

try:
    zip_data = requests.get(shapefile_url, timeout=10).content
    with zipfile.ZipFile(BytesIO(zip_data)) as zf:
        shp_path = [name for name in zf.namelist() if name.endswith('.shp')][0]
        gdf = gpd.read_file(zf.open(shp_path))
    for _, row in gdf.iterrows():
        color_map = {
            "MRGL": "green",
            "SLGT": "yellow",
            "ENH": "orange",
            "MDT": "red",
            "HIGH": "purple"
        }
        color = color_map.get(row["LABEL"], "gray")
        geom = row["geometry"]
        if geom.geom_type == "Polygon":
            folium.GeoJson(
                data=geom.__geo_interface__,
                style_function=lambda x, color=color: {
                    'fillColor': color,
                    'color': color,
                    'weight': 2,
                    'fillOpacity': 0.25
                },
                tooltip=row["LABEL"]
            ).add_to(m)
except Exception as e:
    if used_yesterday:
        st.caption("⚠️ Using yesterday’s SPC outlook (today’s not yet available)")
    st.warning("SPC shapefile outlook overlay unavailable.")
except Exception as e:
    st.warning("SPC categorical outlook image currently unavailable.")

# 🧭 SPC Surface Boundary Layer
if boundary_data and "features" in boundary_data:
    updated = boundary_data.get("features", [{}])[0].get("properties", {}).get("time", None)
    if updated:
        timestamp = datetime.fromtimestamp(updated / 1000).astimezone(ZoneInfo("America/Chicago"))
        st.caption(f"Last updated: {timestamp.strftime('%b %d, %I:%M %p %Z')}")
    st.markdown("**🧭 Surface Boundaries from SPC**")
    for front in boundary_data["features"]:
        props = front.get("properties", {})
        f_type = props.get("type", "Boundary")
        f_label = props.get("label", "")
        st.markdown(f"- {f_type}: {f_label}")
elif boundary_data:
    st.info("No SPC boundaries are currently active.")
else:
    st.info("SPC surface boundary data currently unavailable.")

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
    st.rerun()

# 🌧 MRMS Radar Image (via NOAA)
radar_url = f"https://radar.weather.gov/ridge/standard/KFWS_loop.gif?{int(time())}"
st.image(radar_url, caption="NWS Radar (KFWS)", use_container_width=True)

# Forecast Data
forecast = get_tomorrowio_data(lat, lon)
if not forecast:
    st.stop()

# Open-Meteo fallback for CAPE/CIN
try:
    openmeteo_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=cape,cin&timezone=auto"
    openmeteo_data = requests.get(openmeteo_url).json()
    openmeteo_hours = openmeteo_data['hourly']
    openmeteo_times = openmeteo_hours['time']
    openmeteo_cape = openmeteo_hours['cape'][:12]
    openmeteo_cin = openmeteo_hours['cin'][:12]
except:
    openmeteo_cape = [0]*12
    openmeteo_cin = [0]*12

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
    "cape": h["values"].get("cap") if h["values"].get("cap") not in [None, 0] else openmeteo_cape[i],
    "cin": h["values"].get("cin") if h["values"].get("cin") not in [None, 0] else openmeteo_cin[i],
    "shear": abs(h["values"].get("windSpeed500hpa", 0) - h["values"].get("windSpeed1000hpa", 0)),
    "srh": h["values"].get("stormRelativeHelicity", 0)
} for i, h in enumerate(hours[:12])])

def calculate_risk(row):
    score = 0
    month = datetime.now().month

    # Determine season
    if month in [3, 4, 5]:  # Spring
        season = 'spring'
    elif month in [6, 7, 8]:  # Summer
        season = 'summer'
    else:  # Fall
        season = 'fall'

    # CAPE
    if season == 'spring':
        if row["cape"] >= 3000: score += 25
        elif row["cape"] >= 2000: score += 20
        elif row["cape"] >= 1000: score += 10
    elif season == 'summer':
        if row["cape"] >= 4000: score += 30
        elif row["cape"] >= 3000: score += 20
        elif row["cape"] >= 2000: score += 10
    else:  # fall
        if row["cape"] >= 1500: score += 20
        elif row["cape"] >= 1000: score += 10
        elif row["cape"] >= 500: score += 5

    # Wind Gusts
    if row["gusts"] >= 60: score += 20
    elif row["gusts"] >= 45: score += 10

    # Precipitation
    if row["precip"] >= 2: score += 10
    elif row["precip"] >= 1: score += 5

    # Dew point & Humidity
    if row["dew"] >= 70: score += 10
    elif row["dew"] >= 65 and row["humidity"] >= 70: score += 5

    # CIN (inhibitor)
    if row["cin"] <= -100:
        score -= 20
    elif -100 < row["cin"] <= -50:
        score -= 10
    elif row["cin"] >= 0:
        score += 5

    # Shear (0-6 km bulk shear)
    if season == 'spring':
        if row["shear"] >= 50: score += 15
        elif row["shear"] >= 40: score += 10
        elif row["shear"] >= 30: score += 5
    elif season == 'summer':
        if row["shear"] >= 30: score += 10
        elif row["shear"] >= 20: score += 5
    else:  # fall
        if row["shear"] >= 50: score += 15
        elif row["shear"] >= 40: score += 10
        elif row["shear"] >= 30: score += 5

    # SRH
    if season in ['spring', 'fall']:
        if row["srh"] >= 250: score += 10
        elif row["srh"] >= 150: score += 5
    elif season == 'summer':
        if row["srh"] >= 150: score += 5

    return max(min(score, 100), 0)

df["risk"] = df.apply(calculate_risk, axis=1)

row = df.iloc[0]

# 🌪️🌡️ Current Severe Indices
st.markdown("## Current Severe Indices")
cols = st.columns(5)

with cols[0]:
    st.markdown(f"**CAPE**")
    st.markdown(f"<div style='font-size: 28px'>{row['cape']:.0f} J/kg</div>", unsafe_allow_html=True)
    cape_val = row["cape"]
    cape_color = "#ff4d4d" if cape_val >= 3000 else "#ffaa00" if cape_val >= 1500 else "#2ecc71"
    cape_emoji = "🌪️" if cape_val >= 3000 else "⚠️" if cape_val >= 1500 else "✅"
    cape_width = max(min(cape_val / 40, 100), 5)
    st.markdown(f"{cape_emoji} <div style='height: 12px; width: {cape_width}%; background-color: {cape_color}; border-radius: 6px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

with cols[1]:
    st.markdown(f"**Shear (ΔSpeed)**")
    st.markdown(f"<div style='font-size: 28px'>{row['shear']:.1f} mph</div>", unsafe_allow_html=True)
    shear_val = row["shear"]
    shear_color = "#ff4d4d" if shear_val >= 40 else "#ffaa00" if shear_val >= 30 else "#2ecc71"
    shear_emoji = "💨" if shear_val >= 40 else "⚠️" if shear_val >= 30 else "✅"
    shear_width = max(min(shear_val, 100), 5)
    st.markdown(f"{shear_emoji} <div style='height: 12px; width: {shear_width}%; background-color: {shear_color}; border-radius: 6px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

with cols[2]:
    st.markdown(f"**SRH**")
    st.markdown(f"<div style='font-size: 28px'>{row['srh']:.0f} m²/s²</div>", unsafe_allow_html=True)
    srh_val = row["srh"]
    srh_color = "#ff4d4d" if srh_val >= 150 else "#ffaa00" if srh_val >= 100 else "#2ecc71"
    srh_emoji = "🌀" if srh_val >= 150 else "⚠️" if srh_val >= 100 else "✅"
    srh_width = max(min(srh_val / 2, 100), 5)
    st.markdown(f"{srh_emoji} <div style='height: 12px; width: {srh_width}%; background-color: {srh_color}; border-radius: 6px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

with cols[3]:
    st.markdown(f"**Dew Point**")
    st.markdown(f"<div style='font-size: 28px'>{row['dew']:.0f} °F</div>", unsafe_allow_html=True)
    dew_val = row["dew"]
    dew_color = "#ff4d4d" if dew_val >= 70 else "#ffaa00" if dew_val >= 60 else "#2ecc71"
    dew_emoji = "💧" if dew_val >= 70 else "⚠️" if dew_val >= 60 else "✅"
    dew_width = max(min((dew_val - 50) * 4, 100), 5)
    st.markdown(f"{dew_emoji} <div style='height: 12px; width: {dew_width}%; background-color: {dew_color}; border-radius: 6px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

with cols[4]:
    st.markdown(f"**CIN**")
    st.markdown(f"<div style='font-size: 28px'>{row['cin']:.0f} J/kg</div>", unsafe_allow_html=True)
    cin_val = row["cin"]
    cin_color = "#2ecc71" if cin_val >= -50 else "#ffaa00" if cin_val >= -100 else "#ff4d4d"
    cin_emoji = "✅" if cin_val >= -50 else "⚠️" if cin_val >= -100 else "⛔"
    cin_width = max(min(abs(cin_val) / 2, 100), 5)
    st.markdown(f"{cin_emoji} <div style='height: 12px; width: {cin_width}%; background-color: {cin_color}; border-radius: 6px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# 📡 SPC Mesoscale Discussion Trigger Check
spc_mcd_url = "https://mesoanalysis.spc.noaa.gov/json/srh/srh_0_1km.json"
try:
    headers = {"User-Agent": "Mozilla/5.0"}
    spc_response = requests.get(spc_mcd_url, headers=headers, timeout=5).json()
    trigger_active = any(feature.get("properties", {}).get("value", 0) >= 100 for feature in spc_response.get("features", []))
    if trigger_active:
        st.markdown("### 🛰️ SPC Mesoanalysis Suggests Trigger Active")
        st.markdown("Based on current SPC 0–1 km SRH values, a surface boundary or mesoscale trigger is likely influencing the area.")
except Exception as e:
    st.info("SPC mesoanalysis data currently unavailable. Falling back to internal trigger logic.")

# 🧭 Trigger Potential Estimate (Fallback)
trigger_score = 0
trigger_tooltip = []
month = datetime.now().month
if month in [3, 4, 5]: season = 'spring'
elif month in [6, 7, 8]: season = 'summer'
else: season = 'fall'

# Season-specific logic
if season == 'spring':
    if df["cin"].iloc[0] < -100 and df["cin"].iloc[1] > df["cin"].iloc[0]:
        trigger_score += 1
        trigger_tooltip.append("CIN weakening")
    if df["dew"].iloc[1] - df["dew"].iloc[0] > 2:
        trigger_score += 1
        trigger_tooltip.append("Dew point rising")
    if df["shear"].iloc[1] > df["shear"].iloc[0] and df["shear"].iloc[1] > 30:
        trigger_score += 1
        trigger_tooltip.append("Shear increasing")
    if df["precip"].iloc[0] >= 0.05:
        trigger_score += 1
        trigger_tooltip.append("Precip detected")
elif season == 'summer':
    if df["dew"].iloc[1] > 70 and df["cin"].iloc[0] > -50: trigger_score += 1
    if df["cape"].iloc[0] > 3500: trigger_score += 1
    if df["precip"].iloc[0] >= 0.1: trigger_score += 1
    if df["shear"].iloc[1] > 20: trigger_score += 1
else:  # fall
    if df["shear"].iloc[0] > 40: trigger_score += 1
    if df["dew"].iloc[0] >= 60: trigger_score += 1
    if df["precip"].iloc[0] >= 0.1: trigger_score += 1
    if df["srh"].iloc[0] > 150: trigger_score += 1

if trigger_score >= 3:
    trigger_emoji, trigger_msg, trigger_color = "⛔", "Active trigger likely", "#ff4d4d"
elif trigger_score == 2:
    trigger_emoji, trigger_msg, trigger_color = "⚠️", "Trigger potential present", "#ffaa00"
else:
    trigger_emoji, trigger_msg, trigger_color = "✅", "No obvious trigger yet", "#2ecc71"

st.markdown(f"**Season Profile Active:** `{season.title()}`")
tooltip_text = ', '.join(trigger_tooltip) if trigger_tooltip else 'No active signals'
st.markdown(f"**Trigger Mechanism Signal:** {trigger_msg} 🛈 <span title='{tooltip_text}' style='cursor: help;'>[?]</span>", unsafe_allow_html=True)
st.markdown(f"{trigger_emoji} <div style='height: 20px; width: {trigger_score * 25}%; background-color: {trigger_color}; border-radius: 4px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# ✅ Storm Readiness Score (CAPE + CIN)
if season == 'spring':
    readiness = row["cape"] - abs(row["cin"])
    thresholds = [500, 1000]
elif season == 'summer':
    readiness = row["cape"] - abs(row["cin"])
    thresholds = [1000, 1500]
else:
    readiness = row["cape"] - abs(row["cin"])
    thresholds = [250, 750]

readiness_color = "#2ecc71" if readiness < thresholds[0] else "#ffaa00" if readiness < thresholds[1] else "#ff4d4d"
readiness_emoji = "✅" if readiness < thresholds[0] else "⚠️" if readiness < thresholds[1] else "⛔"
readiness_width = max(min(readiness / 40, 100), 5)
st.markdown(f"**Storm Readiness:** {readiness:.0f} (CAPE - |CIN|)")
st.markdown(f"{readiness_emoji} <div style='height: 20px; width: {readiness_width}%; background-color: {readiness_color}; border-radius: 4px; transition: width 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# 🔥 Current Risk Bar
current_risk = df.iloc[0]["risk"]
risk_color = '#ff4d4d' if current_risk >= 70 else '#ffaa00' if current_risk >= 40 else '#2ecc71'
st.markdown(f"**Current Severe Weather Risk:** {current_risk}/100")
st.markdown(f"<div style='height: 20px; width: {current_risk}%; background-color: {risk_color}; border-radius: 4px; transition: width 0.8s ease-in-out, background-color 0.8s ease-in-out;'></div>", unsafe_allow_html=True)

# 📈 Risk Trend Line (Plotly)
st.subheader("Severe Weather Risk Trend")
risk_chart = go.Figure()
risk_chart.add_trace(go.Scatter(
    x=df["time"],
    y=df["risk"],
    mode="lines+markers",
    line=dict(color="#e74c3c"),
    marker=dict(size=10, color=df["risk"], colorscale="RdYlGn_r", showscale=True),
    name="Risk Score",
    hovertemplate="Time: %{x}<br>Risk: %{y} <extra></extra>"
))
risk_chart.update_layout(
    title=f"{season.title()} Risk Profile",
    yaxis=dict(title="Risk Score", range=[0, 100]),
    xaxis=dict(title="Time", tickangle=-45),
    height=300,
    margin=dict(l=20, r=20, t=30, b=80),
    showlegend=False
)
st.plotly_chart(risk_chart, use_container_width=True)

# 📊 CAPE & CIN Trend (Plotly)
st.subheader("CAPE & CIN Trend")
cape_cin_chart = go.Figure()
cape_cin_chart.add_trace(go.Scatter(
    x=df["time"],
    y=df["cape"],
    mode="lines+markers",
    name="CAPE",
    line=dict(color="orange"),
    marker=dict(symbol="circle"),
    hovertemplate="Time: %{x}<br>CAPE: %{y} J/kg<extra></extra>"
))
cape_cin_chart.add_trace(go.Scatter(
    x=df["time"],
    y=df["cin"],
    mode="lines+markers",
    name="CIN",
    line=dict(color="purple", dash="dash"),
    marker=dict(symbol="x"),
    hovertemplate="Time: %{x}<br>CIN: %{y} J/kg<extra></extra>"
))
cape_cin_chart.update_layout(
    title=f"{season.title()} Instability Profile",
    yaxis=dict(title="J/kg"),
    xaxis=dict(title="Time", tickangle=-45),
    height=300,
    margin=dict(l=20, r=20, t=30, b=80),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(cape_cin_chart, use_container_width=True)