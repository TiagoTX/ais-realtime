import streamlit as st
import folium
from folium.plugins import MeasureControl
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import dotenv_values
from pathlib import Path
from html import escape
from datetime import timezone

PROJECT_ROOT = Path(__file__).resolve().parent

colorscheme = [
    "#e6007e", "#377eb8", "#2e7d32", "#984ea3",
    "#d2691e", "#a65628", "#e41a1c", "#008b8b",
    "#556b2f", "#4169e1", "#8b008b", "#455a64",
]

def fetchDB():
    config = dotenv_values(
        PROJECT_ROOT / ".env.gui",
        interpolate=False,
    )

    required = (
        "SIBDB_HOST",
        "SIBDB_NAME",
        "SIBDB_READER_USER",
        "SIBDB_READER_PASSWORD",
        "SIBDB_ASSET_TABLE",
    )
    missing = [name for name in required if not config.get(name)]

    if missing:
        raise ValueError("Missing GUI settings: " + ", ".join(missing))

    query = sql.SQL("""
        SELECT DISTINCT ON (asset_name)
            asset_name, lat, lon, received_at
        FROM {}
        WHERE asset_name IS NOT NULL
          AND asset_name <> ''
          AND received_at IS NOT NULL
          AND lat BETWEEN -90 AND 90
          AND lon BETWEEN -180 AND 180
        ORDER BY
            asset_name,
            received_at DESC NULLS LAST,
            id DESC
    """).format(
        sql.Identifier("public", config["SIBDB_ASSET_TABLE"])
    )

    conn = psycopg2.connect(
        host=config["SIBDB_HOST"],
        port=config.get("SIBDB_PORT") or "5432",
        database=config["SIBDB_NAME"],
        user=config["SIBDB_READER_USER"],
        password=config["SIBDB_READER_PASSWORD"],
        connect_timeout=5,
    )

    try:
        conn.set_session(readonly=True, autocommit=False)

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
    finally:
        conn.close()

    return rows

def asset_icon(asset_name, color):
    label = escape(str(asset_name))

    icon_html = f"""
        <div style="position: relative; width: 18px; height: 18px;">
            <svg width="18" height="18" viewBox="0 0 18 18">
                <path
                    d="M9 0 L16 18 L9 13 L2 18 Z"
                    fill="{color}"
                />
            </svg>
            <div style="
                position: absolute;
                top: 23px;
                left: 50%;
                transform: translateX(-50%);
                background: {color};
                color: white;
                padding: 2px 5px;
                font-size: 11px;
                font-weight: bold;
                white-space: nowrap;
            ">
                {label}
            </div>
        </div>
    """

    return folium.DivIcon(
        html=icon_html,
        icon_size=(18, 18),
        icon_anchor=(9, 9),
        popup_anchor=(0, -9),
        class_name="asset-marker",
    )



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

        refresh_clicked = st.button("Refresh map", key="refresh_map")

    with st.bottom:
        st.caption(
            "© 2026 INESC TEC - MIT License | fabio.d.pacheco@inesctec.pt | tiago.a.teixeira@inesctec.pt"
        )

    return{
        "polling_minutes": polling_minutes,
        "target_minutes": target_minutes,
        "refresh_clicked": refresh_clicked,
    }
 
def mapit(assets, asset_colors):
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

    for asset in assets:
        name = asset["asset_name"]
        lat = float(asset["lat"])
        lon = float(asset["lon"])
        color = asset_colors[name]

        source_time = asset["received_at"].astimezone(
            timezone.utc
        ).isoformat()

        popup = (
            f"<b>Asset:</b> {escape(str(name))}<br>"
            f"<b>Latitude:</b> {lat:.6f}<br>"
            f"<b>Longitude:</b> {lon:.6f}<br>"
            f"<b>Source time (UTC):</b> {source_time}"
        )

        folium.Marker(
            location=[lat, lon],
            icon=asset_icon(name, color),
            popup=folium.Popup(popup, max_width=320),
        ).add_to(m)

    folium.LayerControl(position="topright").add_to(m)

    return m

    

def loop():
    settings = winlayout()
    st.logo("https://repositorio.inesctec.pt/assets/images/dspace-logo.svg")

    if "assets" not in st.session_state or settings["refresh_clicked"]:
        try:
            assets = fetchDB()
        except (psycopg2.Error, ValueError, OSError):
            st.session_state.read_error = (
                "Could not load asset positions from local SIBDB."
            )
        else:
            st.session_state.assets = assets
            st.session_state.read_error = None

    if st.session_state.get("read_error"):
        st.error(st.session_state.read_error)

    assets = st.session_state.get("assets", [])

    with st.sidebar:
        st.caption(f"{len(assets)} assets loaded")

    if "asset_colors" not in st.session_state:
        st.session_state.asset_colors = {}

    asset_colors = st.session_state.asset_colors

    for asset in assets:
        name = asset["asset_name"]

        if name not in asset_colors:
            asset_colors[name] = colorscheme[
                len(asset_colors) % len(colorscheme)
            ]

    m = mapit(assets, asset_colors)

    st.iframe(m.get_root().render(), height=800)

loop()