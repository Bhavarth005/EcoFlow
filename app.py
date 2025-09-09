import streamlit as st
import geopandas as gpd
import numpy as np
import pandas as pd
import pydeck as pdk
import time
import datetime
import subprocess
import pytz

st.set_page_config(page_title="EcoFlow Traffic App", page_icon="🚦")
st.title("EcoFlow Traffic Congestion & Signal Simulation")

# Define IST timezone
ist = pytz.timezone('Asia/Kolkata')


# Function to run process.py with a given time string (HH:MM:SS)
def run_congestion_prediction(time_str):
    result = subprocess.run(['python', 'process.py', time_str], capture_output=True, text=True)
    if result.returncode != 0:
        st.error(f"Prediction script failed:\n{result.stderr}")
        return False
    else:
        st.info(f"Prediction script output:\n{result.stdout}")
        return True


# Function to load zones and roads, adding default congestion if missing
@st.cache_data(show_spinner=False)
def load_data():
    zones = gpd.read_file('zones_with_congestion.gpkg')
    roads = gpd.read_file('roads_with_congestion.gpkg')

    # Defensive: Add congestion column if missing to avoid key errors
    if 'congestion' not in zones.columns:
        zones['congestion'] = 0.0
    if 'congestion' not in roads.columns:
        roads['congestion'] = 0.0

    return zones, roads

# On first load, run congestion prediction with selected IST time
if 'congestion_loaded' not in st.session_state:
    current_time_str = datetime.datetime.now(ist).strftime("%H:%M:%S")
    with st.spinner(f"Running congestion prediction for {current_time_str} IST..."):
        success = run_congestion_prediction(current_time_str)
        if success:
            st.session_state.congestion_loaded = True
        else:
            st.warning("Using previously loaded congestion data due to prediction failure.")
    # Load fresh after running prediction
    zones_gdf, roads_gdf = load_data()
else:
    # Normal load if already loaded once
    zones_gdf, roads_gdf = load_data()


# Button to run congestion prediction on demand with selected IST time
if st.sidebar.button("Run Congestion Prediction", key='run_pred_button'):
    current_time_str = datetime.datetime.now(ist).strftime("%H:%M:%S")
    with st.spinner(f"Running congestion prediction for {current_time_str} IST..."):
        success = run_congestion_prediction(current_time_str)
        if success:
            zones_gdf, roads_gdf = load_data()
            st.success("Congestion prediction updated.")
        else:
            st.error("Congestion prediction failed.")


# Sidebar UI
show_circles = st.sidebar.checkbox('Show Congestion Circles', True, key='show_circles')
show_roads = st.sidebar.checkbox('Show Traffic Light Layer', True, key='show_roads')


def congestion_to_color(c):
    r = int(255 * c)
    g = int(255 * (1 - c))
    return [r, g, 0]


def build_zone_layer(selected_zone=None):
    if selected_zone and selected_zone in zones_gdf['zone_id'].values:
        zone = zones_gdf[zones_gdf['zone_id'] == selected_zone]
        centroid = zone.geometry.centroid.iloc[0]
        color = congestion_to_color(zone['congestion'].iloc[0])
        data = pd.DataFrame({
            'lon': [centroid.x],
            'lat': [centroid.y],
            'congestion': zone['congestion'],
            'color': [color]
        })
        return pdk.Layer(
            "ScatterplotLayer",
            data=data,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius=700,
            opacity=0.3,
            pickable=True,
            radius_min_pixels=25,
        ), centroid.x, centroid.y, 14
    else:
        colors = zones_gdf['congestion'].apply(congestion_to_color).tolist()
        centroids = zones_gdf.geometry.centroid
        data = pd.DataFrame({
            'lon': centroids.x,
            'lat': centroids.y,
            'congestion': zones_gdf['congestion'],
            'color': colors
        })
        return pdk.Layer(
            "ScatterplotLayer",
            data=data,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius=700,
            opacity=0.2,
            pickable=True,
            radius_min_pixels=15,
        ), zones_gdf.geometry.centroid.x.mean(), zones_gdf.geometry.centroid.y.mean(), 12


def phase_offset(road_id, cycle_length=12):
    return hash(road_id) % cycle_length


def simulate_traffic_light(congestion, tick, offset):
    cycle_length = 12
    pos_in_cycle = (tick + offset) % cycle_length
    if congestion > 0.7:
        if pos_in_cycle < 8:
            return 'red'
        elif pos_in_cycle < 10:
            return 'yellow'
        else:
            return 'green'
    elif congestion > 0.3:
        if pos_in_cycle < 5:
            return 'red'
        elif pos_in_cycle < 7:
            return 'yellow'
        else:
            return 'green'
    else:
        if pos_in_cycle < 3:
            return 'red'
        elif pos_in_cycle < 5:
            return 'yellow'
        else:
            return 'green'


light_color_map = {
    'red': [255, 0, 0],
    'yellow': [255, 255, 0],
    'green': [0, 255, 0]
}


def build_road_layer(tick):
    colors = []
    for _, row in roads_gdf.iterrows():
        offset = phase_offset(row['id'])
        state = simulate_traffic_light(row['congestion'], tick, offset)
        colors.append(light_color_map[state])
    roads_gdf['light_color'] = colors
    return pdk.Layer(
        "PathLayer",
        data=roads_gdf,
        get_path='geometry.coordinates',
        get_color='light_color',
        width_scale=10,
        width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
    )


zone_names = [''] + zones_gdf['zone_id'].tolist()  # Or a more user-friendly column
selected_zone = st.sidebar.selectbox("Search Zone", options=zone_names)
# Initial view params
zone_layer, center_lon, center_lat, zoom_level = build_zone_layer(selected_zone)
road_layer = build_road_layer(0)


view_state = pdk.ViewState(
    longitude=center_lon,
    latitude=center_lat,
    zoom=zoom_level,
    pitch=0,
)


placeholder = st.empty()
tick = 0


# To detect map clicks, Streamlit does not have built-in support, so we simulate reset by a "Clear Selection" button
clear_clicked = st.sidebar.button("Clear Zone Selection")


if clear_clicked:
    selected_zone = ''


while True:
    # If selection cleared, show all zones
    zone_layer, center_lon, center_lat, zoom_level = build_zone_layer(selected_zone)
    road_layer = build_road_layer(tick)


    view_state = pdk.ViewState(
        longitude=center_lon,
        latitude=center_lat,
        zoom=zoom_level,
        pitch=0,
    )


    layers = []
    if show_circles:
        layers.append(zone_layer)
    if show_roads:
        layers.append(road_layer)


    r = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip={"text": "{congestion}"},
        # map_style='mapbox://styles/mapbox/dark-v10',
    )
    placeholder.pydeck_chart(r)


    tick += 1
    time.sleep(3)
