from time import monotonic
from math import ceil, asin, cos, radians, sin, sqrt

import streamlit as st
import folium
from folium.plugins import MeasureControl
from folium.utilities import parse_options
from branca.element import Element
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import dotenv_values
from pathlib import Path
from html import escape
from datetime import timezone
from poller import polling_worker

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



def distance_nm(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    earth_radius_nm = 6_371_000 / 1_852
    return 2 * earth_radius_nm * asin(sqrt(min(1.0, haversine)))



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

@st.fragment(run_every=1)
def polling_controls():
    
    polling_minutes = st.number_input(
            "Polling interval (minutes)",
            min_value=1,
            value=5,
            step=1,
            key="polling_minutes",
    )

    if st.button("Start polling", key="start_polling"):
        polling_worker.start(polling_minutes)

    if st.button("Stop polling", key="stop_polling"):
        polling_worker.stop()

    polling_worker.heartbeat()

    status = polling_worker.status()
    if status["phase"] == "stopping":
        st.caption("Stopping after current batch")
    else:
        st.caption(f"Polling status: {status['phase']}")

    countdown_s = status["next_run_at"]
    if countdown_s is None:
        st.caption("Update in: N/A")
    else:
        countdown_s = max(0, ceil(countdown_s - monotonic()))
        minutes, seconds = divmod(countdown_s, 60)
        st.caption(f"Update in: {minutes:02d}:{seconds:02d}")

    if status["error"] is not None:
        st.caption("Last polling batch failed.")





def winlayout():
    st.set_page_config(page_title="AIS-Realtime", layout="wide")

    with st.sidebar:
        st.title("AIS-Realtime")

        st.subheader("Adapter")

        polling_controls()

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

asset_map_component = st.components.v2.component(
    "asset_map",
    html='<iframe id="live-map" title="Live asset map" sandbox="allow-scripts"></iframe>',
    css="#live-map { width: 100%; height: 800px; border: 0; }",
    js="""
        export default function ({ parentElement, data }) {
            const frame = parentElement.querySelector("#live-map");

            if (!frame.hasAttribute("srcdoc")) {
                const channel = new MessageChannel();
                frame.reportPort = channel.port1;

                frame.addEventListener("load", () => {
                    frame.contentWindow.postMessage("connect-reports", "*", [channel.port2]);
                }, { once: true });

                frame.srcdoc = data.base_html;
            }

            frame.reportPort.postMessage(data.reports);
        }
    """,
)

@st.fragment(run_every=1)
def map_panel():
    with st.sidebar:
        refresh_clicked = st.button("Refresh assets", key="refresh_map")

    latest_batch_stamp = polling_worker.status()["last_successful_end"]
    assets_loaded = False
    
    # Updates on new batch, refresh button or first load 
    if (
        "last_map_batch_stamp" not in st.session_state
        or refresh_clicked
        or latest_batch_stamp != st.session_state.last_map_batch_stamp
    ):
        st.session_state.last_map_batch_stamp = latest_batch_stamp
        try:
            assets = fetchDB()
        except (psycopg2.Error, ValueError, OSError):
            st.session_state.read_error = (
                "Could not load asset positions from local SIBDB."
            )
        else:
            st.session_state.assets = assets
            st.session_state.read_error = None
            assets_loaded = True

    if st.session_state.get("read_error"):
        st.error(st.session_state.read_error)

    assets = st.session_state.get("assets", [])

    with st.sidebar:
        st.caption(f"{len(assets)} assets loaded")

        centre_mode = st.selectbox(
            "Radius filter",
            ["Off", "Centre on asset", "Manual coordinates"],
            key="radius_centre_mode",
        )
        centre = None

        if centre_mode == "Centre on asset":
            assets_by_mmsi = {asset["asset_name"]: asset for asset in assets}
            centre_mmsi = st.selectbox(
                "Pick asset (MMSI)",
                options=list(assets_by_mmsi),
                index=None,
                key="radius_centre_mmsi",
            )
            centre_asset = assets_by_mmsi.get(centre_mmsi)
            if centre_asset is not None:
                centre = (float(centre_asset["lat"]), float(centre_asset["lon"]))
                st.caption(f"Centre: {centre[0]:.6f}, {centre[1]:.6f}")

        elif centre_mode == "Manual coordinates":
            latitude = st.number_input(
                "Centre latitude", -90.0, 90.0, value=None, format="%.6f"
            )
            longitude = st.number_input(
                "Centre longitude", -180.0, 180.0, value=None, format="%.6f"
            )
            if latitude is not None and longitude is not None:
                centre = (latitude, longitude)

        radius_nm = st.number_input(
            "Radius (nautical miles)",
            min_value=0.1,
            value=10.0,
            step=0.1,
            key="radius_nm",
        )

    if "asset_map_base_html" not in st.session_state:
        base_map = mapit()
        map_page = base_map.get_root()

        map_page.script.add_child(
            Element(f'const liveMapName = "{base_map.get_name()}";')
        )

        map_page.html.add_child(Element("""
            <script>
                const markersByMmsi = new Map();

                function makeAssetPopup(report) {
                    const popup = document.createElement("div");
                    const fields = [
                        ["Asset", report.mmsi],
                        ["Latitude", report.lat.toFixed(6)],
                        ["Longitude", report.lon.toFixed(6)],
                        ["Source time (UTC)", report.received_at],
                    ];

                    for (const [label, value] of fields) {
                        const line = document.createElement("div");
                        const title = document.createElement("strong");
                        title.textContent = label + ": ";
                        line.append(title, value);
                        popup.append(line);
                    }

                    return popup;
                }

                window.addEventListener("message", (event) => {
                    if (event.source !== window.parent || event.data !== "connect-reports") {
                        return;
                    }

                    const port = event.ports[0];
                    if (!port) {
                        return;
                    }

                    port.onmessage = ({ data: reports }) => {
                        if (!Array.isArray(reports)) {
                            return;
                        }

                        const map = window[liveMapName];

                        const visibleMmsis = new Set(reports.map(report => report.mmsi));

                        for (const [mmsi, current] of markersByMmsi) {
                            if (!visibleMmsis.has(mmsi)) {
                                map.removeLayer(current.marker);
                                markersByMmsi.delete(mmsi);
                            }
                        }

                        for (const report of reports) {
                            const current = markersByMmsi.get(report.mmsi);
                            if (current) {
                                const previous = current.report;
                                const moved = report.lat !== previous.lat
                                    || report.lon !== previous.lon;

                                if (moved) {
                                    current.marker.setLatLng([report.lat, report.lon]);
                                }

                                if (moved || report.received_at !== previous.received_at) {
                                    current.marker.setPopupContent(makeAssetPopup(report));
                                    current.report = report;
                                }
                                continue;
                            }

                            const marker = L.marker([report.lat, report.lon], {
                                icon: L.divIcon(report.icon),
                            }).addTo(map);

                            marker.bindPopup(makeAssetPopup(report), { maxWidth: 320 });

                            markersByMmsi.set(report.mmsi, { marker, report });
                        }
                    };
                });
            </script>
        """))

        st.session_state.asset_map_base_html = map_page.render()

    if assets_loaded or "live_map_reports" not in st.session_state:
        asset_colors = st.session_state.setdefault("asset_colors", {})
        reports = []
        for asset in assets:
            name = asset["asset_name"]
            received_at = asset["received_at"].astimezone(timezone.utc).isoformat()
            if name not in asset_colors:
                asset_colors[name] = colorscheme[
                    len(asset_colors) % len(colorscheme)
                ]

            reports.append({
                "mmsi": str(name),
                "lat": float(asset["lat"]),
                "lon": float(asset["lon"]),
                "received_at": received_at,
                "icon": parse_options(**asset_icon(name, asset_colors[name]).options),
            })
        st.session_state.live_map_reports = reports

    visible_reports = st.session_state.live_map_reports
    if centre is not None:
        centre_lat, centre_lon = centre
        visible_reports = [
            report
            for report in visible_reports
            if distance_nm(centre_lat, centre_lon, report["lat"], report["lon"])
            <= radius_nm
        ]

    asset_map_component(
        key = "live_asset_map",
        data = {
            "base_html": st.session_state.asset_map_base_html,
            "reports": visible_reports,
        }
    )

def loop():
    winlayout()
    st.logo("https://repositorio.inesctec.pt/assets/images/dspace-logo.svg")
    map_panel()


loop()
