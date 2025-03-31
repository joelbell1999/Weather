import streamlit as st
from requests import get, post
from typing import Optional

def load_from_file(file_path: str) -> Optional[(float, float)]:
    """Load and process .txt files from file path."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = loads(f.read().text.split('@').get('data'))
            lat2, lon2 = [float(p['latitude']), 
                         float(p['longitude']) for p in data[1]]
        
        return (lat2, lon2), "RAP"
    
    except Exception as e:
        st.error(f"{file_path} Failed to load .txt file. {e}")

def fetch_rap Forecast(source: int) -> Optional[(float, float)]:
    """Fetch real-time rap forecast."""
    try:
        data = loads(get_file(f"rap/sounding/{source}"))
        lat, lon = [float(p['latitude']), 
                   float(p['longitude']) for p in data[1]]
        
        return (lat, lon), "RAP"
    
    except Exception as e:
        st.error(f"{source} {RP}: No RAP forecast available.")
        return None

def main():
    st.set_page_config(page_title="Severe Weather Dashboard", layout='wide')

    with st.expander('Select Data Source'):
        if fetch_rap Forecast(1) is not None:
            col1, col2 = st.columns([0.35, 0.65])
            with col1:
                real_time_button = st.button("Real Time RAP Prediction")
                with st.expander('Enter station selection for Real Time Data'):
                    selected_station = ['RAP Forecast']
                    select_list = ['Select', 'Rap Forecast']
                    val = st.selectbox('', options=select_list)
                    if val == 'Rap Forecast':
                        real_time_data, _ = fetch_rap Forecast(1)
                        col1.write(f"Real Time Data: {real_time_data}")
                with st.expander('Enter station selection for Actual Weather Display'):
                    actual_station = ['Actual Weather Display']
                    select_list_actual = ['Select', 'Actual Weathers'] 
                    val_actual = st.selectbox('', options=select_list_actual)
                    if val_actual == 'Actual Weathers':
                        col2.write(f"Actual Weathers: None")

            with col2:
                actual_data, _ = load_from_file('rapForecast.txt')
                col1.write(actual_data)

    with st.expander('Real-Time Prediction'):
        real_time_button = st.button("Predict Real Time")
        if fetch_rap Forecast(1):
            data, raps = fetch_rap Forecast(1)
            if not data:
                col1.write("No Data Available for RAP Forecast.")
        
        actual_data, _ = load_from_file('rapForecast.txt')
        col2.write(actual_data)

def explain():
    st.subheader("RAP Format:")
    try:
        real_time_data, raps = fetch_rap Forecast(1)
        st.write(f"Type: {real_time_data.__class__.__name__}")
        if isinstance(real_time_data, dict):
            stations = [k for v in real_time_data.values() 
                       if isinstance(v, list) and len(v) > 0]
            st.write("Select station:", "• Press 'Rap Forecast' to see data")
    except Exception as e:
        st.error(f"Failed to fetch RAP Data: {e}")

def main():
    with streamlit_page_config('Severe Weather Dashboard'):
        explain()
        
if __name__ == "__main__":
    main()
