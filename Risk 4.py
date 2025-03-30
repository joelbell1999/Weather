import requests

def get_current_location():
    ipinfo_response = requests.get('https://ipinfo.io/json')
    if ipinfo_response.status_code != 200:
        return None
    location_data = ipinfo_response.json()
    lat, lon = location_data['loc'].split(',')
    return float(lat), float(lon)

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

def get_weather_data():
    location = get_current_location()
    if not location:
        return None

    lat, lon = location
    precip_last_24hrs = get_precipitation_past_24hrs(lat, lon)
    weather_data = []

    # Open-Meteo API for current forecast
    open_meteo_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,windspeed_10m,windgusts_10m,weathercode,precipitation,precipitation_probability,cloudcover,dewpoint_2m,cape,relative_humidity_2m,surface_pressure"
        f"&forecast_days=1&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch&timezone=auto"
    )

    open_meteo_response = requests.get(open_meteo_url)

    if open_meteo_response.status_code == 200:
        open_meteo_hourly = open_meteo_response.json().get('hourly', {})
        times = open_meteo_hourly.get('time', [])
        temperatures = open_meteo_hourly.get('temperature_2m', [])
        wind_speeds = open_meteo_hourly.get('windspeed_10m', [])
        wind_gusts = open_meteo_hourly.get('windgusts_10m', [])
        weather_codes = open_meteo_hourly.get('weathercode', [])
        precipitations = open_meteo_hourly.get('precipitation', [])
        precip_probs = open_meteo_hourly.get('precipitation_probability', [])
        cloud_covers = open_meteo_hourly.get('cloudcover', [])
        dewpoints = open_meteo_hourly.get('dewpoint_2m', [])
        capes = open_meteo_hourly.get('cape', [])
        humidities = open_meteo_hourly.get('relative_humidity_2m', [])
        pressures = open_meteo_hourly.get('surface_pressure', [])

        for i in range(3):  # Next 3 hours
            weather_data.append({
                'time': times[i],
                'temperature': temperatures[i],
                'windSpeed': wind_speeds[i],
                'windGusts': wind_gusts[i],
                'weatherCode': weather_codes[i],
                'precipitation': precipitations[i],
                'precipProbability': precip_probs[i],
                'cloudCover': cloud_covers[i],
                'dewpoint': dewpoints[i],
                'cape': capes[i],
                'humidity': humidities[i],
                'pressure': pressures[i]
            })

    return weather_data, precip_last_24hrs

def calculate_severe_risk(period):
    risk = 0

    if period['windSpeed'] >= 58 or period['windGusts'] >= 60:
        risk += 30
    elif period['windSpeed'] >= 40 or period['windGusts'] >= 50:
        risk += 20
    elif period['windSpeed'] >= 30 or period['windGusts'] >= 40:
        risk += 10

    cape = period['cape']
    if cape >= 3500:
        risk += 30
    elif cape >= 2500:
        risk += 20
    elif cape >= 1500:
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

# Example execution
weather_data, precip_last_24hrs = get_weather_data()

print(f"Precipitation in Last 24 Hours: {precip_last_24hrs} inches\n")
print("DFW Area Comprehensive Weather Data and Severe Risk Factor (Next 3 hours):")
for period in weather_data:
    risk = calculate_severe_risk(period)
    print(f"Time: {period['time']}")
    print(f"Temperature: {period['temperature']} °F")
    print(f"Wind Speed: {period['windSpeed']} mph, Gusts: {period['windGusts']} mph")
    print(f"Weather Code: {period['weatherCode']}")
    print(f"Precipitation: {period['precipitation']} inches, Probability: {period['precipProbability']}%")
    print(f"Cloud Cover: {period['cloudCover']}%, Humidity: {period['humidity']}%, Dewpoint: {period['dewpoint']} °F")
    print(f"CAPE: {period['cape']} J/kg, Pressure: {period['pressure']} hPa")
    print(f"Severe Risk Factor: {risk}/100\n")
