"""ShelfCast Stage 6 local viewer (Streamlit) -- reveal loop + spread/suggestion.

Launch from the project root:

    streamlit run app.py

Stage 4 was a read-only predicted-temperature viewer. Stage 5 added a controlled
reveal loop: select a provisional candidate profile, see the Stage 3 predicted
curve, then press "Reveal actual measurements" to reveal that ONE profile's
hidden historical readings. The app overlays the real readings at their true
recorded depths, fits an in-memory temporary model from the original training
rows plus only that profile's revealed rows, and shows the original vs updated
predicted curves for the selected site plus a before/after comparison,
map-marker update, and numeric prediction change at 20 m for one nearby
still-hidden candidate site. A "Reset replay" button returns to the pre-reveal
state and the original saved model.

Stage 6 adds two exploratory views on top of that, keeping the Stage 3
prediction and the Stage 5 reveal charts intact. It fits five reproducible
versions of the ExtraTrees model by resampling WHOLE training candidate profiles
(never individual readings) and shades the min-to-max range of their predicted
curves at the selected site -- labeled "spread across five models, an exploratory
measure, not a calibrated confidence interval." It also suggests ONE eligible
historical candidate profile to TEST (never an optimal site or boat route),
chosen by the five models' disagreement at the 5 m and 10 m requested prediction
levels. After a reveal, the spread and suggestion are refit from the training
rows plus only the one revealed profile. Stage 6 reuses `fit_model` and
`predict_temperatures` unchanged and adds no forecast, calibrated uncertainty,
oxygen, weather, new research model, or deployment.

Data boundary: Data/splits/heldout_points.csv is opened ONLY by
shelfcast.reveal.read_revealed_profile, only after the reveal click, and only for
the selected profile_id's rows. Every pre-reveal path (startup, map, cache,
selection, pre-reveal prediction) uses shelfcast/viewer.py, which never opens the
heldout file or the hidden columns of profile_summary.csv. The temporary model is
held in memory only and is NEVER written over Results/model.joblib.

Historical replay: training candidate profiles ended (end_time) strictly before
the 2024-08-06T00:00:00Z UTC cutoff; the selected hidden profile started
(start_time) on or after it. This is a replay, not a live or future forecast,
and no deployment. The Stage 6 five-model spread band is an exploratory range,
not a calibrated uncertainty band or confidence interval. The Stage 6 suggestion
is a profile to test (highest five-model disagreement among eligible historical
candidates), never an optimal site or an operational boat route.

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

from shelfcast import reveal, spread, viewer
from shelfcast.config import DEFAULT_DEPTH_GRID, SPREAD_SCORE_DEPTHS, TRAIN_POINTS_PATH
from shelfcast.model import lookup_candidate_site, predict_temperatures

# Ocean palette -- restrained, declarative.
DEEP_NAVY = [12, 44, 84]
SEA_FOAM = [86, 168, 190]
CANDIDATE_GOLD = [224, 168, 72]
ACTUAL_CORAL = [214, 92, 84]
UPDATED_TEAL = [38, 150, 142]
WARMER_RED = [200, 70, 60]
COOLER_BLUE = [48, 96, 176]
SPREAD_MIST = [138, 172, 196]  # the shaded five-model spread band

NEARBY_DEPTH = reveal.NEARBY_DEPTH_M  # 20 m, a single requested prediction level

ATTRIBUTION = (
    "Ocean temperature observations from the eMOLT (Environmental Monitors on "
    "Lobster Traps and Large Trawlers) program, retrieved via the ondeckdata "
    "ERDDAP server (erddap.ondeckdata.com), covering 1-7 Aug 2024. Free use and "
    "redistribution; not intended for legal use."
)


def _format_lat(lat: float) -> str:
    hemi = "N" if lat >= 0 else "S"
    return f"{abs(lat):.4f} B0{hemi}".replace("B0", "\u00b0")


def _format_lon(lon: float) -> str:
    hemi = "E" if lon >= 0 else "W"
    return f"{abs(lon):.4f} \u00b0{hemi}"


def _page_setup() -> None:
    st.set_page_config(
        page_title="ShelfCast reveal loop + spread",
        page_icon="\U0001f30a",
        layout="wide",
    )
    st.title("\U0001f30a ShelfCast")
    st.caption(
        "A local historical replay of the Stage 3 temperature predictor, with a "
        "reveal loop, a five-model spread band (an exploratory range, not a "
        "calibrated confidence interval), and one suggested candidate profile to "
        "test. The model was trained only on candidate profiles that ended "
        "before the 2024-08-06 00:00 UTC cutoff; the hidden profiles you can "
        "reveal started on or after it. This is a replay, not a live or future "
        "forecast."
    )


# -- cached, pre-reveal loaders (never touch the heldout file) --------------
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


@st.cache_data(show_spinner=False)
def _load_training_rows() -> pd.DataFrame:
    # Full source columns (including profile_id) for the Stage 6 spread fit. A
    # pre-reveal observational input -- never the heldout file.
    return pd.read_csv(TRAIN_POINTS_PATH)


@st.cache_resource(show_spinner=False)
def _spread_models():
    # The five reproducible pre-reveal spread models, fit once (profile-level
    # resampling, fixed seeds). Held in memory only; never written to disk.
    return spread.fit_spread_models(_load_training_rows())


def _predicted_curve(model_obj, site: dict, label: str) -> pd.DataFrame:
    table = viewer.predict_site_table(model_obj, site, list(DEFAULT_DEPTH_GRID))
    table["series"] = label
    return table


def _render_map(
    train_df: pd.DataFrame,
    sites_df: pd.DataFrame,
    nearby_marker: dict | None = None,
) -> None:
    st.subheader("Locations")
    legend = (
        "Recorded positions only. "
        f"<span style='color:rgb({SEA_FOAM[0]},{SEA_FOAM[1]},{SEA_FOAM[2]})'>"
        "\u25cf training locations</span> and "
        f"<span style='color:rgb({CANDIDATE_GOLD[0]},{CANDIDATE_GOLD[1]},{CANDIDATE_GOLD[2]})'>"
        "\u25cf candidate profiles</span> (replay sites)."
    )
    if nearby_marker is not None:
        legend += (
            " After a reveal, the nearby still-hidden site is recolored by its "
            f"predicted-temperature change at {NEARBY_DEPTH:.0f} m "
            f"(<span style='color:rgb({WARMER_RED[0]},{WARMER_RED[1]},{WARMER_RED[2]})'>"
            "\u25cf warmer</span> / "
            f"<span style='color:rgb({COOLER_BLUE[0]},{COOLER_BLUE[1]},{COOLER_BLUE[2]})'>"
            "\u25cf cooler</span>)."
        )
    legend += (
        " Candidate markers are **provisional candidate profiles**, never "
        "verified fishing tows or casts."
    )
    st.markdown(legend, unsafe_allow_html=True)

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
    layers = [training_layer, candidate_layer]
    tooltip = {"text": "candidate profile {profile_id}"}

    if nearby_marker is not None:
        warmer = nearby_marker["delta"] >= 0
        color = WARMER_RED if warmer else COOLER_BLUE
        marker_df = pd.DataFrame([nearby_marker])
        nearby_layer = pdk.Layer(
            "ScatterplotLayer",
            data=marker_df,
            get_position="[longitude, latitude]",
            get_fill_color=[color[0], color[1], color[2], 240],
            get_radius=420,
            pickable=True,
        )
        layers.append(nearby_layer)
        tooltip = {
            "text": (
                "nearby candidate profile {profile_id}\n"
                f"predicted @ {NEARBY_DEPTH:.0f} m: "
                "{original_label} \u2192 {updated_label} \u00b0C"
            )
        }

    deck = pdk.Deck(
        map_style="light",
        initial_view_state=view_state,
        layers=layers,
        tooltip=tooltip,
    )
    st.pydeck_chart(deck, width="stretch")


def _render_prediction(model_obj, site: dict, profile_id: int) -> None:
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Recorded latitude", _format_lat(site["latitude"]))
    col_b.metric("Recorded longitude", _format_lon(site["longitude"]))
    col_c.metric("UTC start time", site["start_time"].strftime("%Y-%m-%d %H:%M:%SZ"))

    table = viewer.predict_site_table(model_obj, site, list(DEFAULT_DEPTH_GRID))
    st.subheader(
        f"Predicted temperature at depth \u2014 candidate profile {profile_id}"
    )
    st.caption(
        "This chart shows the original saved model's predictions only, at the "
        "requested prediction levels (not a claim about the actual bottom "
        "depth). It is not a forecast and carries no uncertainty or confidence "
        "claim."
    )
    chart = (
        alt.Chart(table)
        .mark_line(
            point=True, color=f"rgb({DEEP_NAVY[0]},{DEEP_NAVY[1]},{DEEP_NAVY[2]})"
        )
        .encode(
            x=alt.X("temperature_c:Q", title="Predicted temperature (\u00b0C)"),
            y=alt.Y(
                "depth_m:Q",
                title="Requested prediction depth (m)",
                scale=alt.Scale(reverse=True),
            ),
            tooltip=[
                alt.Tooltip("depth_m:Q", title="Depth (m)"),
                alt.Tooltip("temperature_c:Q", title="Temp (\u00b0C)", format=".3f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(chart, width="stretch")


def _render_spread(models, site: dict, profile_id: int) -> None:
    """Shaded min-to-max band of the five spread models, with the Stage 3 line.

    An exploratory measure, not a calibrated confidence interval (Req 2.1, 2.4,
    2.5). The Stage 3 prediction from the original saved model is drawn on top so
    the baseline stays visible (Req 2.2).
    """
    band = spread.spread_table(models, site, list(DEFAULT_DEPTH_GRID))
    st.subheader(f"Five-model spread \u2014 candidate profile {profile_id}")
    st.caption(
        "Spread across five models \u2014 an exploratory measure, not a "
        "calibrated confidence interval. Each model was fit by resampling whole "
        "candidate profiles. Depths are requested prediction levels, not a claim "
        "about actual bottom depth."
    )
    area = (
        alt.Chart(band)
        .mark_area(
            opacity=0.35,
            color=f"rgb({SPREAD_MIST[0]},{SPREAD_MIST[1]},{SPREAD_MIST[2]})",
        )
        .encode(
            x=alt.X("temp_min:Q", title="Predicted temperature (\u00b0C)"),
            x2=alt.X2("temp_max:Q"),
            y=alt.Y(
                "depth_m:Q",
                title="Requested prediction depth (m)",
                scale=alt.Scale(reverse=True),
            ),
            tooltip=[
                alt.Tooltip("depth_m:Q", title="Depth (m)"),
                alt.Tooltip("temp_min:Q", title="Min (\u00b0C)", format=".3f"),
                alt.Tooltip("temp_max:Q", title="Max (\u00b0C)", format=".3f"),
            ],
        )
    )
    stage3 = viewer.predict_site_table(_load_model(), site, list(DEFAULT_DEPTH_GRID))
    line = (
        alt.Chart(stage3)
        .mark_line(
            point=True, color=f"rgb({DEEP_NAVY[0]},{DEEP_NAVY[1]},{DEEP_NAVY[2]})"
        )
        .encode(
            x=alt.X("temperature_c:Q"),
            y=alt.Y("depth_m:Q", scale=alt.Scale(reverse=True)),
            tooltip=[
                alt.Tooltip("depth_m:Q", title="Depth (m)"),
                alt.Tooltip("temperature_c:Q", title="Stage 3 (\u00b0C)", format=".3f"),
            ],
        )
    )
    st.altair_chart((area + line).properties(height=360), width="stretch")


def _render_suggestion(
    models, sites_df: pd.DataFrame, selected_id: int, site: dict, after_time
) -> None:
    """One suggested candidate profile to TEST, by five-model disagreement.

    The suggestion favors the eligible candidate where the five models disagree
    most at the 5 m and 10 m requested prediction levels (Req 5.1, 5.2). It is a
    profile to test, never an optimal site or an operational boat route (Req 5.3).
    Predictions only -- no hidden value is read for any candidate (Req 5.5).
    """
    suggestion = spread.suggest_candidate(
        models, sites_df, selected_id, site, after_time
    )
    st.subheader("Suggested next measurement")
    if suggestion is None:
        st.info(
            "No eligible candidate is available for a suggestion (need a "
            f"candidate at least {reveal.MIN_NEARBY_KM:.0f} km from the selected "
            "site whose recorded start time is after the current replay cutoff)."
        )
        return
    levels = " and ".join(f"{d:.0f} m" for d in SPREAD_SCORE_DEPTHS)
    left, right = st.columns([2, 3])
    left.metric(
        label=f"Candidate profile {suggestion['profile_id']}",
        value=f"score {suggestion['score']:.3f}",
    )
    right.markdown(
        f"**A profile to test** \u2014 not an optimal site or a boat route. "
        f"Among the eligible historical candidate profiles, candidate profile "
        f"**{suggestion['profile_id']}** has the highest five-model disagreement "
        f"about temperature at {levels}."
    )
    right.caption(
        "The score is the summed min-to-max prediction spread across the five "
        f"models at {levels}. Predictions only \u2014 this candidate's actual "
        "measurements are never read."
    )


def _render_selected_reveal_chart(
    model_obj, temp_model, site: dict, revealed_df: pd.DataFrame, profile_id: int
) -> None:
    original = _predicted_curve(model_obj, site, "original prediction")
    updated = _predicted_curve(temp_model, site, "updated prediction")
    curves = pd.concat([original, updated], ignore_index=True)

    lines = (
        alt.Chart(curves)
        .mark_line(point=True)
        .encode(
            x=alt.X("temperature_c:Q", title="Temperature (\u00b0C)"),
            y=alt.Y("depth_m:Q", title="Depth (m)", scale=alt.Scale(reverse=True)),
            color=alt.Color(
                "series:N",
                title=None,
                scale=alt.Scale(
                    domain=["original prediction", "updated prediction"],
                    range=[
                        f"rgb({DEEP_NAVY[0]},{DEEP_NAVY[1]},{DEEP_NAVY[2]})",
                        f"rgb({UPDATED_TEAL[0]},{UPDATED_TEAL[1]},{UPDATED_TEAL[2]})",
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("series:N"),
                alt.Tooltip("depth_m:Q", title="Depth (m)"),
                alt.Tooltip("temperature_c:Q", title="Temp (\u00b0C)", format=".3f"),
            ],
        )
    )
    actual = revealed_df.rename(columns={"temperature_c": "temp", "depth_m": "depth"})
    points = (
        alt.Chart(actual)
        .mark_point(
            filled=True,
            size=70,
            shape="diamond",
            color=f"rgb({ACTUAL_CORAL[0]},{ACTUAL_CORAL[1]},{ACTUAL_CORAL[2]})",
        )
        .encode(
            x=alt.X("temp:Q"),
            y=alt.Y("depth:Q", scale=alt.Scale(reverse=True)),
            tooltip=[
                alt.Tooltip("depth:Q", title="Recorded depth (m)"),
                alt.Tooltip("temp:Q", title="Actual temp (\u00b0C)", format=".3f"),
            ],
        )
    )
    st.subheader(f"Revealed measurements \u2014 candidate profile {profile_id}")
    st.caption(
        "Coral diamonds are the revealed actual readings at their true recorded "
        "depths (not snapped to the requested prediction levels). Lines are the "
        "original and the temporary updated model predictions at the requested "
        "prediction levels."
    )
    st.altair_chart((lines + points).properties(height=400), width="stretch")


def _render_nearby(model_obj, temp_model, nearby_site: dict, nearby_id: int) -> dict:
    original = _predicted_curve(model_obj, nearby_site, "original prediction")
    updated = _predicted_curve(temp_model, nearby_site, "updated prediction")
    curves = pd.concat([original, updated], ignore_index=True)
    delta = reveal.nearby_site_delta(model_obj, temp_model, nearby_site, NEARBY_DEPTH)

    st.subheader(f"Nearby still-hidden candidate profile {nearby_id}")
    st.caption(
        "Predictions only \u2014 this site's actual measurements are never read. "
        f"The map marker and the metric below show the predicted change at "
        f"{NEARBY_DEPTH:.0f} m."
    )
    left, right = st.columns([3, 2])
    chart = (
        alt.Chart(curves)
        .mark_line(point=True)
        .encode(
            x=alt.X("temperature_c:Q", title="Predicted temperature (\u00b0C)"),
            y=alt.Y(
                "depth_m:Q",
                title="Requested prediction depth (m)",
                scale=alt.Scale(reverse=True),
            ),
            color=alt.Color(
                "series:N",
                title=None,
                scale=alt.Scale(
                    domain=["original prediction", "updated prediction"],
                    range=[
                        f"rgb({DEEP_NAVY[0]},{DEEP_NAVY[1]},{DEEP_NAVY[2]})",
                        f"rgb({UPDATED_TEAL[0]},{UPDATED_TEAL[1]},{UPDATED_TEAL[2]})",
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip("series:N"),
                alt.Tooltip("depth_m:Q", title="Depth (m)"),
                alt.Tooltip("temperature_c:Q", title="Temp (\u00b0C)", format=".3f"),
            ],
        )
        .properties(height=360)
    )
    left.altair_chart(chart, width="stretch")
    right.metric(
        label=f"Predicted temp @ {NEARBY_DEPTH:.0f} m",
        value=f"{delta['updated']:.3f} \u00b0C",
        delta=f"{delta['delta']:+.3f} \u00b0C vs original",
    )
    right.caption(
        f"Original {delta['original']:.3f} \u00b0C \u2192 updated "
        f"{delta['updated']:.3f} \u00b0C after revealing the selected profile."
    )
    return {
        "profile_id": nearby_id,
        "latitude": nearby_site["latitude"],
        "longitude": nearby_site["longitude"],
        "delta": delta["delta"],
        "original_label": f"{delta['original']:.3f}",
        "updated_label": f"{delta['updated']:.3f}",
    }


def _render_context(metadata: dict) -> None:
    with st.expander("Sources, units, and limitations", expanded=True):
        st.markdown(
            "- **Units:** temperature in degrees Celsius (\u00b0C), depth in metres (m).\n"
            "- **Historical replay:** training candidate profiles ended before the "
            "2024-08-06 00:00 UTC cutoff; the hidden profiles you can reveal started "
            "on or after it. Not a live reading or a future forecast.\n"
            "- **Provisional candidate profiles:** the starter eMOLT data omits the "
            "`tow_id` and `segment_type` columns, so these groups are inferred from "
            "recorded position and time proximity and are **not** verified fishing "
            "tows or casts. They are never labeled as a tow or a cast.\n"
            "- **Unknown bottom depth:** the standard depths are requested prediction "
            "levels only; they do not establish the actual bottom depth at a site.\n"
            "- **Temporary model:** the updated model after a reveal lives in memory "
            "only and never overwrites the saved model.\n"
            "- **Five-model spread:** the shaded band is the range of five models "
            "fit by resampling whole candidate profiles. It is an exploratory "
            "measure, **not** a calibrated confidence interval or a forecast.\n"
            "- **Suggested next measurement:** a profile to **test**, chosen by the "
            "five models' disagreement at 5 m and 10 m. It is never an optimal "
            "site or an operational boat route.\n"
            f"- **Dataset attribution:** {ATTRIBUTION}"
        )
        st.caption(
            "Model: "
            f"{metadata.get('feature_order')} \u00b7 seed {metadata.get('random_state')} \u00b7 "
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

    # Initialize reveal session state once.
    for key in reveal.REVEAL_STATE_KEYS:
        st.session_state.setdefault(key, None)

    st.subheader("Select a candidate profile")
    profile_ids = sorted(int(p) for p in sites_df["profile_id"].unique())
    profile_id = int(
        st.selectbox(
            "Candidate profile id",
            options=profile_ids,
            help="A provisional candidate profile from the Stage 2 replay set.",
        )
    )

    # Top-of-rerun guard: discard any reveal that is not for the current id, so a
    # selection change returns to the original saved model and pre-reveal view.
    reveal.reset_reveal_state(st.session_state, profile_id)

    try:
        site = lookup_candidate_site(profile_id)
    except (KeyError, ValueError) as exc:
        st.error(f"Candidate-profile lookup failed: {exc}")
        st.stop()
        return

    # Reveal / reset controls.
    c1, c2, _ = st.columns([1, 1, 3])
    reveal_clicked = c1.button("Reveal actual measurements", type="primary")
    reset_clicked = c2.button("Reset replay")
    if reset_clicked:
        reveal.reset_reveal_state(st.session_state, None)

    # Only this branch opens the heldout file, and only for the selected id.
    if reveal_clicked:
        try:
            revealed = reveal.read_revealed_profile(profile_id)
        except FileNotFoundError:
            st.error(
                "The hidden measurements file (Data/splits/heldout_points.csv) "
                "was not found. Run the Stage 2 split first:\n\n"
                "    python Scripts/split_replay.py"
            )
            revealed = None
        except KeyError:
            st.error(
                f"No hidden measurements found for candidate profile {profile_id}."
            )
            revealed = None
        if revealed is not None and len(revealed) == 0:
            st.warning(
                f"No actual measurements are available for candidate profile {profile_id}."
            )
            revealed = None
        if revealed is not None:
            try:
                train_rows = reveal.load_training_rows()
                temp_model = reveal.fit_temporary_model(train_rows, revealed)
            except (ValueError, OSError) as exc:
                st.error(f"The temporary model could not be fit: {exc}")
            else:
                st.session_state["revealed_profile_id"] = profile_id
                st.session_state["revealed_df"] = revealed
                st.session_state["temp_model"] = temp_model

    revealed_df = st.session_state.get("revealed_df")
    temp_model = st.session_state.get("temp_model")
    has_reveal = (
        st.session_state.get("revealed_profile_id") == profile_id
        and revealed_df is not None
        and temp_model is not None
    )

    nearby_marker = None
    if has_reveal:
        after_time = reveal.revealed_final_time(revealed_df)
        nearby_id = reveal.nearest_candidate_site(profile_id, sites_df, after_time)
        if nearby_id is not None:
            nearby_site = lookup_candidate_site(int(nearby_id))
            nearby_marker = _render_nearby_prep(
                model_obj, temp_model, nearby_site, int(nearby_id)
            )

    _render_map(train_df, sites_df, nearby_marker)

    # Stage 6 spread + suggestion. Before a reveal these use the cached five
    # pre-reveal models and the selected site's recorded start time as the
    # eligibility cutoff. After a reveal they use five UPDATED models fit from
    # the training rows plus ONLY the one revealed profile, and the revealed
    # profile's final recorded measurement time as the cutoff. The updated
    # models are reveal-scoped session state, so a selection change or Reset
    # replay (via reveal.reset_reveal_state) drops them automatically.
    spread_error = None
    spread_after_time = site["start_time"]
    try:
        if has_reveal:
            if st.session_state.get("spread_models_updated") is None:
                st.session_state["spread_models_updated"] = spread.fit_spread_models(
                    _load_training_rows(), revealed_df
                )
            spread_models = st.session_state["spread_models_updated"]
            spread_after_time = reveal.revealed_final_time(revealed_df)
        else:
            spread_models = _spread_models()
    except (ValueError, OSError) as exc:
        spread_models = None
        spread_error = str(exc)

    if has_reveal:
        _render_selected_reveal_chart(
            model_obj, temp_model, site, revealed_df, profile_id
        )
        if nearby_marker is not None:
            _render_nearby(
                model_obj,
                temp_model,
                lookup_candidate_site(int(nearby_marker["profile_id"])),
                int(nearby_marker["profile_id"]),
            )
        else:
            st.info(
                "No eligible nearby site (need a still-hidden candidate at least "
                f"{reveal.MIN_NEARBY_KM:.0f} km away that starts after this "
                "profile's final recorded measurement)."
            )
    else:
        _render_prediction(model_obj, site, profile_id)

    if spread_models is not None:
        _render_spread(spread_models, site, profile_id)
        _render_suggestion(spread_models, sites_df, profile_id, site, spread_after_time)
    else:
        st.info(
            "The five-model spread and the suggestion are unavailable: "
            f"{spread_error}"
        )

    _render_context(metadata)


def _render_nearby_prep(
    model_obj, temp_model, nearby_site: dict, nearby_id: int
) -> dict:
    """Compute the nearby marker payload (predictions only) for the map layer."""
    delta = reveal.nearby_site_delta(model_obj, temp_model, nearby_site, NEARBY_DEPTH)
    return {
        "profile_id": nearby_id,
        "latitude": nearby_site["latitude"],
        "longitude": nearby_site["longitude"],
        "delta": delta["delta"],
        "original_label": f"{delta['original']:.3f}",
        "updated_label": f"{delta['updated']:.3f}",
    }


if __name__ == "__main__":
    main()
else:
    main()
