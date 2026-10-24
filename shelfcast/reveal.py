"""ShelfCast Stage 5 reveal-loop helpers.

The ONE module permitted to open Data/splits/heldout_points.csv, and only after
the explicit "Reveal actual measurements" click. read_revealed_profile filters
to the single selected profile_id and returns ONLY that profile's rows; no other
profile's rows are ever returned, stored, used for fitting, or shown. Every
function here is pure and importable, so the viewer's reveal behavior is testable
without launching Streamlit.

Data boundary (Stage 5): pre-reveal/startup/map/cache/selection paths live in
shelfcast/viewer.py and never touch the heldout file. This module adds the single
narrow post-reveal exception. It never reads the hidden summary columns of
Data/processed/profile_summary.csv, and the temporary model is held in memory
only -- it is NEVER written over Results/model.joblib or any other file.

Historical replay (Stage 2 split): training candidate profiles ended (end_time)
strictly before the 2024-08-06T00:00:00Z UTC cutoff, while the selected hidden
profile started (start_time) on or after it.

Stage 1 groups are provisional CANDIDATE PROFILES inferred from recorded position
and time proximity -- never verified fishing tows or casts.
"""

from __future__ import annotations

import math

import pandas as pd

from shelfcast import model
from shelfcast.config import HELDOUT_POINTS_PATH, TRAIN_POINTS_PATH

# The full revealed columns -- the values the reveal exists to show, read only
# after the explicit click and only for the selected profile_id.
REVEALED_COLUMNS = [
    "time",
    "latitude",
    "longitude",
    "depth_m",
    "temperature_c",
    "profile_id",
]

# Source columns fit_model needs from the combined training + revealed frame.
FIT_SOURCE_COLUMNS = ["latitude", "longitude", "depth_m", "time", "temperature_c"]

# Session-state keys the reveal holds, all bound to the selected profile_id.
REVEAL_STATE_KEYS = ("revealed_profile_id", "revealed_df", "temp_model")

# The single requested prediction level used for the nearby-site map/delta.
NEARBY_DEPTH_M = 20.0

# Minimum separation (km) a candidate must have from the revealed site to be an
# eligible nearby comparison -- excludes effectively co-located profiles.
MIN_NEARBY_KM = 1.0

# Mean Earth radius (km) for the haversine great-circle distance.
_EARTH_RADIUS_KM = 6371.0088


def read_revealed_profile(
    profile_id: int, path: str = HELDOUT_POINTS_PATH
) -> pd.DataFrame:
    """Return ONLY the selected profile's rows from heldout_points.csv.

    The ONLY code path permitted to open heldout_points.csv, and only after the
    explicit reveal click. Filters to profile_id and returns a frame with columns
    REVEALED_COLUMNS; no other profile's rows are ever returned (Req 3.1, 3.2,
    3.5). Raises KeyError naming the id when it is absent (Req 3.4).

    Raises FileNotFoundError when the heldout file is missing so the caller can
    report it gracefully (Req 3.8).
    """
    frame = pd.read_csv(path, usecols=REVEALED_COLUMNS)
    selected = frame[frame["profile_id"] == profile_id].copy()
    if len(selected) == 0:
        raise KeyError(
            f"profile_id {profile_id} not found in heldout points"
        )
    return selected[REVEALED_COLUMNS].reset_index(drop=True)


def load_training_rows(path: str = TRAIN_POINTS_PATH) -> pd.DataFrame:
    """Return the training source rows for the temporary refit.

    Reads only train_points.csv (a pre-reveal observational input, Req 5.1).
    """
    return pd.read_csv(path)


def fit_temporary_model(train_df: pd.DataFrame, revealed_df: pd.DataFrame):
    """Fit an in-memory temporary model from training rows + the revealed rows.

    Concatenates the training rows with ONLY the selected profile's revealed rows
    (restricted to the fit source columns), reuses shelfcast.model.fit_model
    verbatim, and returns the fitted estimator. NEVER writes to disk, so
    Results/model.joblib is left untouched (Req 5.1, 5.3).
    """
    combined = pd.concat(
        [train_df[FIT_SOURCE_COLUMNS], revealed_df[FIT_SOURCE_COLUMNS]],
        ignore_index=True,
    )
    return model.fit_model(combined)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points."""
    rlat1, rlon1, rlat2, rlon2 = map(
        math.radians, (float(lat1), float(lon1), float(lat2), float(lon2))
    )
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def revealed_final_time(revealed_df: pd.DataFrame):
    """UTC timestamp of the revealed profile's last recorded measurement."""
    times = pd.to_datetime(revealed_df["time"], utc=True)
    return times.max()


def nearest_candidate_site(
    selected_id: int, sites_df: pd.DataFrame, after_time
) -> int | None:
    """profile_id of the nearest ELIGIBLE still-hidden candidate, else None.

    A candidate is eligible when it is not the selected profile, lies at least
    MIN_NEARBY_KM (1 km) from the selected site by great-circle distance, and has
    a recorded start_time strictly after `after_time` (the revealed profile's
    final recorded measurement). Among eligible candidates the nearest by
    kilometre distance wins, ties broken by lowest profile_id. Returns None when
    no candidate is eligible (Req 6.1, 6.6). Reads only the candidate-site columns
    already in sites_df; never the heldout file (Req 6.5).
    """
    selected_rows = sites_df[sites_df["profile_id"] == selected_id]
    if len(selected_rows) == 0:
        raise KeyError(f"selected profile_id {selected_id} not in candidate sites")
    sel = selected_rows.iloc[0]
    after = pd.to_datetime(after_time, utc=True)

    best_id = None
    best_key = None
    for _, row in sites_df.iterrows():
        pid = int(row["profile_id"])
        if pid == selected_id:
            continue
        dist_km = haversine_km(
            sel["latitude"], sel["longitude"], row["latitude"], row["longitude"]
        )
        if dist_km < MIN_NEARBY_KM:
            continue
        start = pd.to_datetime(row["start_time"], utc=True)
        if not (start > after):
            continue
        key = (dist_km, pid)  # nearest first, tie-break on lowest profile_id
        if best_key is None or key < best_key:
            best_key = key
            best_id = pid
    return best_id


def nearby_site_delta(
    original_model, temp_model, site: dict, depth: float = NEARBY_DEPTH_M
) -> dict:
    """Original and temporary predicted temperature at one requested level.

    Returns {"original", "updated", "delta", "depth"} where original/updated are
    each model's predicted temperature at the requested prediction level (default
    20 m) for the nearby site's recorded coordinates and UTC start time, and
    delta == updated - original. Predictions ONLY via the reused
    shelfcast.model.predict_temperatures -- never reads any heldout temperature or
    depth for the nearby site (Req 6.3, 6.4, 6.5).
    """
    original = model.predict_temperatures(
        original_model, site["latitude"], site["longitude"], site["start_time"], [depth]
    )[0]
    updated = model.predict_temperatures(
        temp_model, site["latitude"], site["longitude"], site["start_time"], [depth]
    )[0]
    return {
        "original": float(original),
        "updated": float(updated),
        "delta": float(updated) - float(original),
        "depth": float(depth),
    }


def reset_reveal_state(session_like, selected_profile_id) -> None:
    """Clear revealed state unless it belongs to the currently selected profile.

    Pure and Streamlit-free: operates on any mapping (st.session_state or a dict).
    The single clear path shared by the top-of-rerun guard and the "Reset replay"
    button. When session_like's stored revealed_profile_id does not equal
    selected_profile_id, discards revealed_profile_id/revealed_df/temp_model so
    the app returns to the original saved model (Req 7.1, 7.3, 7.4, 7.5). Passing
    selected_profile_id=None forces a full clear (the explicit reset case).
    """
    stored = session_like.get("revealed_profile_id")
    if stored != selected_profile_id:
        for key in REVEAL_STATE_KEYS:
            session_like[key] = None


__all__ = [
    "REVEALED_COLUMNS",
    "FIT_SOURCE_COLUMNS",
    "REVEAL_STATE_KEYS",
    "NEARBY_DEPTH_M",
    "MIN_NEARBY_KM",
    "read_revealed_profile",
    "load_training_rows",
    "fit_temporary_model",
    "haversine_km",
    "revealed_final_time",
    "nearest_candidate_site",
    "nearby_site_delta",
    "reset_reveal_state",
]