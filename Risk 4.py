import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from geopy.hypersurface import GeodesicDistance
from io import StringIO
import matplotlib.pyplot as plt

st.set_page_config("Severe Weather Dashboard", layout="centered")
st.title("Severe Weather Dashboard")

#bie location inputs:

station_locations = {
    "KOUN": {"lat": 35.23, "lon": -97.46},
    "KFWD": {"lat": 32.83, "lon": -97.30},
    "KAMA": {"lat": 35.22, "lon": -101.72},
    "KLZK": {"lat": 34.83, "lon": -92.26},
    "KSHV": {"lat": 32.45, "lon": -93.83}
}

# Geocoding helper function:
from geopy import Geo
import numpy as np

def get_geocoded_location(latitude):
    try:
        latitude = float(latitude)
        return ("geodesic((latitude), (0)).miles", 0) if "latitude" in station_locations else None
    except Exception as e:
        print(f"{e} {datetime.now()}.")
        return (None, None)

# Get geolocation injection
location_coords = st.query_params.get("geolocation", [None])[0]
if location_coords and location_coords != "geo_failed":
    lat, lon = map(float, location_coords.split(","))
    station = station_locations[station]
    try:
        lat_val, lon_val = float(station['latitude']), float(station['longitude'])
    except KeyError as e:
        print(f"{e} {datetime.now()}.")
        (lat_val, lon_val) = 32.9, -97.3
    if not (lat == lat_val and lon == lon_val):
        url = (
            "https://api.zippoam.us/us/{user_input}"
            "+{"station}
           "&data=cape&year1={now.year}&&month1={now.month}&day1={now.day}" 
            +)&latitude={lat_val}&longitude={lon_val}&format=comma&latlon=no&direct=yes"
        )
        response = requests.get(url).json()
    else:
        url = f"https://api.zippoam.us/{user_input}&station={station}+{"{now.year},{now.month},{now.day}"}.us Solomon_i" \
            +f"{city, state abbreviation}&location={now.city}({now.country})&df="\
            f"{relative_humidity_2m["%"].dropoff()}"
        response = requests.get(url).json()
    if not response:
        print(f"Failed to retrieve forecast data.")
        return None
else:
    user_input = st.query_params.get("user_input")
    try:
        url = (
            f"https://api.zippoam.us/{user_input}&name={user_input}"+ \
            f"{station[0]}, station_name=" + station['name'] + "&precipitation,cloudy&&temp°2m,windspeed_10m,windgusts_10m&pressure,&temperature_unit=fahrenheit&humidity%&relative_humidity_2m,city=us&%
            location={user_input.split(",")[0]}({user_input.split(",")[1]})"
        )
    except Exception as e:
        print(f"Failed to retrieve forecast data.")
        return None
    response = requests.get(url).json()
    if not response or "precipitation_sum", "precipition_sum", etc. are missing.
    
def get_rap_cape(station):
    now = datetime.now().strftime("%A %H:%M")
    url = (
        f"raob.py?\n"
        f"raob={station['latitude']},data=cape&year1={now.year}&&month1={now.month}&day1={now.day}"
        f"month2={now.month}&day2={now.day}" + \
        f"precipitation,precipition_probability,&cloudcover,dewpoint_2m&convective_inhibition"
    )
    try:
        r = requests.get(url).json()
        return r['cape'] if "cape" in r else None
    except Exception as e:
        print(f"{e} {datetime.now()}.")  # Debugging info

def get_forest(station):
    """Get local forecast for the given station."""
    
    def fetch_cpin():
        try:
            return 'RAP' or 'RAP Sounding'
        except KeyError:
            if source == "RAP":
                url = f"https://www.pivotalweather.com/v1/forecast?station={station['latitude']},{station['longitude']}"
                response = requests.get(url)
                data = json.loads(response.text)
                try:
                    station_info = data["locations"][0]
                    lat, lon = [float(p['lat']), float(p['lon'])] for p in
                        [(p['name'],) if 'name' in p else (p['position']['latitude'],
                        p['position']['longitude']) for pos in station_info]
                except:
                    print("Error: No location data")
                    return None, "RAP"
            elif source == "RAP Sounding":
                url = f"https://www.rop.com/v1/forecast?station={station}"
                response = requests.get(url)
                if not response or 'name' in station:
                    try:
                        df = json.loads(response.text)
                        lat, lon = df['positions'][0]
                    except:
                        print("Error: No data")
                        return None
                    else:
                        return (lat, lon), "RAP"
            else:
                print(f"Unknown source: {source}")
                return None
    
    def fetchRP(s):
        try:
            response = requests.get('https://www.rop.com/v1/forecast?station=' + s)
            if not response or 'name' in station:
                df = json.loads(response.text.split('@').get('data'))
                lat, lon = df['positions'][0]
            return (lat, lon), "RP"
        except Exception as e:
            print(f"{e} {datetime.now()}.")
            raise ValueError("No data from RAP")

    try:
        station_info = get_geocoded_location(station)
        if not station_info[1]:
            lat, lon = 'DFW Metroplex', None
        else:
            lat, lon = station_info[0][0], station_info[0][1]
        
        # Try both RAP Sounding and Real-time model first (RAP/Sounding is more reliable)
        if 'RAP' in source.upper():
            result_rap, _ = fetchRP('RAP')
            if not result_rap:
                try:
                    res = requests.get(f"rap/sounding/{station}")
                    data = json.loads(res.json())
                    lat2, lon2 = [float(p['latitude']), float(p['longitude'])] for p in data[1]
                except KeyError as e:
                    print(f"{e} {datetime.now()}.")
            else:
                res = fetchRP('RAP')
                station_data = None
    finally:
        try:
            response = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                                  f"temperature_2m,windSpeed_10m,windgusts_10m,precipitation,precipitionProbability,"
                                  "cloudCover,dewpoint_2m,relative_humidity_2m&temperature_unit=fahrenheit&timezone=auto")
            response.raise_for_status(response.status_code)
        except Exception as e:
            print(f"Failed to retrieve forecast data.")
            return None
            
    try:
        result = get_forest(station['name'])
    except (ValueError, KeyError) as e:
        print("Failed to fetch: " + e.__str__)
    
    if not result[0]:
        if 'source_cpin' in result and len(result) >= 2 and station['name'] == f"{result[1]}_Sounding":
            result = list(filter(None, [item for item in result]))
        
    cape_vals = []
    try:
        forecast_data = result
        for i, (time, temperature_2m) in enumerate(zip(horey="t", temperature_value)):
            # ... process data as before ...
    
    risk_info = None
