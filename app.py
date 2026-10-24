"""ShelfCast Stage 4 local viewer (Streamlit).

Launch from the project root:

    streamlit run app.py

A thin, read-only viewer over the Stage 3 artifacts. It loads the saved model
and metadata from Results/, shows training and candidate-profile locations on a
map, lets you pick a candidate profile, and charts the Stage 3 predicted
temperatures at the declared standard depths for that site's recorded location
and UTC start time. It reuses shelfcast.model.predict_temperatures unchanged, so
the chart matches the Stage 3 prediction CLI exactly.

Data boundary (carried forward from Stage 3): this app references only the
training points, the candidate-site table, and the Results/ artifacts. It never
opens Data/splits/heldout_points.csv or Data/processed/profile_summary.csv, and
it never displays a hidden temperature or depth. It adds no retraining,
uncertainty, next-site recommendation, forecast, or deployment.

Groups are provisional CANDIDATE PROFILES inferred from recorded position and
time proximity -- never verified fishing tows or casts.
"""

from __future__ import annotations

import os
import sys

# Allow `streamlit run app.py` from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from shelfcast import viewer
from shelfcast.config import DEFAULT_DEPTH_GRID
from shelfcast.model import lookup_candidate_site

# Ocean palette -- restrained, declarative.
DEEP_NAVY = [12, 44, 84]
SEA_FOAM = [86, 168, 190]
CANDIDATE_GOLD = [224, 168, 72]

ATTRIBUTION = (
    "Ocean temperature observations from the eMOLT (Environmental Monitors on "
    "Lobster Traps and Large Trawlers) program, retrieved via the ondeckdata "
    "ERDDAP server (erddap.ondeckdata.com), covering 1-7 Aug 2024. Free use and "
    "redistribution; not intended for legal use."
)


def _format_lat(lat: float) -> str:
    """Latitude with an explicit N/S hemisphere label."""
    hemi = "N" if lat >= 0 else "S"
    return f"{abs(lat):.4f} °{hemi}"


def _format_lon(lon: float) -> str:
    """Longitude with an explicit E/W hemisphere label.

    Study-region longitudes are negative (western hemisphere), so a bare "°E"
    on a negative value is misleading; use the magnitude with the correct side.
    """
    hemi = "E" if lon >= 0 else "W"
    return f"{abs(lon):.4f} °{hemi}"


def _page_setup() -> None:
    st.set_page_config(
        page_title="ShelfCast candidate-profile temperature viewer",
        page_icon="🌊",
        layout="wide",
    )
    st.title("🌊 ShelfCast")
    st.caption(
        "A local, read-only view of the Stage 3 temperature predictor. "
        "Historical replay of eMOLT candidate profiles, not a live or future forecast."
    )


@st.cache_resource(show_spinner=False)
def _load_model():
    return viewer.load_fitted_model()


@st.cache_data(show_spinner=False)
def _load_metadata() -> dict:
    return viewer.load_metadata()


@st.cache_data(show_spinner=False)
def _load_training_locations() -> pd.DataFrame:
    return viewer.load_training_locations()


@st.cache_data(show_spinner=False)
def _load_candidate_sites() -> pd.DataFrame:
    return viewer.load_candidate_sites()


def _render_map(train_df: pd.DataFrame, sites_df: pd.DataFrame) -> None:
    st.subheader("Locations")
    st.markdown(
        "Recorded positions only. "
        f"<span style='color:rgb({SEA_FOAM[0]},{SEA_FOAM[1]},{SEA_FOAM[2]})'>"
        "● training locations</span> and "
        f"<span style='color:rgb({CANDIDATE_GOLD[0]},{CANDIDATE_GOLD[1]},{CANDIDATE_GOLD[2]})'>"
        "● candidate profiles</span> (replay sites). Candidate markers are "
        "**provisional candidate profiles**, never verified fishing tows or casts.",
        unsafe_allow_html=True,
    )

    all_lat = pd.concat([train_df["latitude"], sites_df["latitude"]])
    all_lon = pd.concat([train_df["longitude"], sites_df["longitude"]])
    view_state = pdk.ViewState(
        latitude=float(all_lat.mean()),
        longitude=float(all_lon.mean()),
        zoom=8,
        pitch=0,
    )

    training_layer = pdk.Layer(
        "ScatterplotLayer",
        data=train_df,
        get_position="[longitude, latitude]",
        get_fill_color=[SEA_FOAM[0], SEA_FOAM[1], SEA_FOAM[2], 140],
        get_radius=220,
        pickable=False,
    )
    candidate_layer = pdk.Layer(
        "ScatterplotLayer",
        data=sites_df,
        get_position="[longitude, latitude]",
        get_fill_color=[CANDIDATE_GOLD[0], CANDIDATE_GOLD[1], CANDIDATE_GOLD[2], 220],
        get_radius=320,
        pickable=True,
    )
    deck = pdk.Deck(
        map_style="light",
        initial_view_state=view_state,
        layers=[training_layer, candidate_layer],
        tooltip={"text": "candidate profile {profile_id}"},
    )
    st.pydeck_chart(deck, use_container_width=True)


def _render_prediction(model_obj, site: dict, profile_id: int) -> None:
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Recorded latitude", _format_lat(site["latitude"]))
    col_b.metric("Recorded longitude", _format_lon(site["longitude"]))
    col_c.metric("UTC start time", site["start_time"].strftime("%Y-%m-%d %H:%M:%SZ"))

    table = viewer.predict_site_table(model_obj, site, list(DEFAULT_DEPTH_GRID))

    st.subheader(f"Predicted temperature at depth — candidate profile {profile_id}")
    st.caption(
        "Model predictions only. No forecast, uncertainty, confidence, or "
        "measurement-location recommendation is implied."
    )

    chart = (
        alt.Chart(table)
        .mark_line(
            point=True, color=f"rgb({DEEP_NAVY[0]},{DEEP_NAVY[1]},{DEEP_NAVY[2]})"
        )
        .encode(
            x=alt.X("temperature_c:Q", title="Predicted temperature (°C)"),
            y=alt.Y(
                "depth_m:Q",
                title="Requested prediction depth (m)",
                scale=alt.Scale(reverse=True),
            ),
            tooltip=[
                alt.Tooltip("depth_m:Q", title="Depth (m)"),
                alt.Tooltip("temperature_c:Q", title="Temp (°C)", format=".3f"),
            ],
        )
        .properties(height=380)
    )
    left, right = st.columns([3, 2])
    left.altair_chart(chart, use_container_width=True)
    display = table.rename(
        columns={"depth_m": "Depth (m)", "temperature_c": "Predicted temp (°C)"}
    )
    right.dataframe(display, hide_index=True, use_container_width=True)


def _render_context(metadata: dict) -> None:
    with st.expander("Sources, units, and limitations", expanded=True):
        st.markdown(
            "- **Units:** temperature in degrees Celsius (°C), depth in metres (m).\n"
            "- **Historical replay:** this view replays recorded eMOLT candidate "
            "profiles from 1-7 Aug 2024. It is not a live reading or a future forecast.\n"
            "- **Provisional candidate profiles:** groups are inferred from recorded "
            "position and time proximity and are **not** verified fishing tows or casts.\n"
            "- **Unknown bottom depth:** the standard depths are requested prediction "
            "levels only; they do not establish the actual bottom depth at a site.\n"
            f"- **Dataset attribution:** {ATTRIBUTION}"
        )
        st.caption(
            "Model: "
            f"{metadata.get('feature_order')} · seed {metadata.get('random_state')} · "
            f"trained on {metadata.get('n_rows')} readings across "
            f"{metadata.get('n_candidate_profiles')} candidate profiles."
        )


def main() -> None:
    _page_setup()

    try:
        model_obj = _load_model()
        metadata = _load_metadata()
    except FileNotFoundError:
        st.error(
            "No trained model found under Results/. Run the Stage 3 training "
            "script first:\n\n    python Scripts/train_model.py"
        )
        st.stop()
        return

    try:
        train_df = _load_training_locations()
        sites_df = _load_candidate_sites()
    except (FileNotFoundError, OSError, ValueError) as exc:
        st.error(f"Could not load Stage 2 inputs: {exc}")
        st.stop()
        return

    _render_map(train_df, sites_df)

    st.subheader("Select a candidate profile")
    profile_ids = sorted(int(p) for p in sites_df["profile_id"].unique())
    profile_id = st.selectbox(
        "Candidate profile id",
        options=profile_ids,
        help="A provisional candidate profile from the Stage 2 replay set.",
    )

    try:
        site = lookup_candidate_site(int(profile_id))
    except (KeyError, ValueError) as exc:
        st.error(f"Candidate-profile lookup failed: {exc}")
        st.stop()
        return

    _render_prediction(model_obj, site, int(profile_id))
    _render_context(metadata)


if __name__ == "__main__":
    main()
else:
    # Streamlit executes the module top-to-bottom under `streamlit run`.
    main()
