import streamlit as st
import folium
from folium.plugins import MeasureControl

def winlayout():
    st.set_page_config(page_title="AIS-Realtime", layout="wide")

    with st.sidebar:
        st.title("AIS-Realtime")

        st.subheader("Adapter")

        polling_minutes = st.number_input(
            "Polling interval (minutes)",
            min_value=1,
            value=5,
            step=1,
            key="polling_minutes",
        )

        st.subheader("Display")

        target_minutes = st.number_input(
            "Target reports from the last … minutes",
            min_value=1,
            value=10,
            step=1,
            key="target_minutes",
        )

    with st.bottom:
        st.caption(
            "© 2026 INESC TEC - MIT License | fabio.d.pacheco@inesctec.pt | tiago.a.teixeira@inesctec.pt"
        )

    return{
        "polling_minutes": polling_minutes,
        "target_minutes": target_minutes,
    }

def mapit():
    m = folium.Map(
        location=[41.458747, -8.842215],
        zoom_start=6,
        tiles=None,
        control_scale=True,
    )

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap",
        overlay=False,
        show=False,
    ).add_to(m)

    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr=(
            "Esri, DigitalGlobe, GeoEye, Earthstar Geographics, "
            "CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, "
            "and the GIS User Community"
        ),
        name="Satellite Imagery",
        overlay=False,
        show=True,
    ).add_to(m)

    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS user community",
        name="City Labels & Boundaries",
        overlay=True,
        show=True,
    ).add_to(m)

    m.add_child(MeasureControl(
        position="topleft",
        primary_length_unit="nauticalmiles",
        secondary_length_unit="kilometers",
        primary_area_unit="sqnm",
        secondary_area_unit="sqkilometers",
        active_color="#e41a1c",
        completed_color="#377eb8",
    ))

    folium.LayerControl(position="topright").add_to(m)

    return m

    

def loop():
    settings = winlayout()
    st.logo("https://www.inesctec.pt/INESCTECcomb_EN_mail.png")

    m = mapit()
    st.iframe(m.get_root().render(), height=800)


loop()