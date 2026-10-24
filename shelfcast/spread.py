"""ShelfCast Stage 6 spread + suggestion engine (the Spread_Engine).

Two exploratory capabilities layered on top of the Stage 5 reveal loop:

1. A five-model SPREAD. Fit exactly five reproducible versions of the existing
   ExtraTrees temperature model by resampling WHOLE training candidate profiles
   (profile-level bootstrap), never individual readings, and report the
   minimum-to-maximum range of their predicted temperature at a site. The spread
   is an EXPLORATORY measure, NOT a calibrated confidence interval.

2. A single SUGGESTED next measurement. Score eligible historical candidate
   profiles by how much the five models disagree at the 5 m and 10 m requested
   prediction levels, and pick the one with the highest disagreement. The result
   is a profile to TEST, never an optimal site or an operational boat route.

Every function here is pure, importable, and Streamlit-free so the behavior is
testable without launching the app. The module reuses shelfcast.model.fit_model
and shelfcast.model.predict_temperatures verbatim, and the Stage 5
shelfcast.reveal helpers (haversine_km, revealed_final_time, MIN_NEARBY_KM).

Data boundary (carried forward unchanged): this module reads feature and target
values only from the in-memory frames it is handed -- the Stage 2 training rows
and, after a reveal, ONLY the one selected revealed profile's rows (already read
by shelfcast.reveal.read_revealed_profile) -- plus the candidate-site
coordinate/time columns. It NEVER opens Data/splits/heldout_points.csv and never
reads the hidden summary columns of Data/processed/profile_summary.csv. No spread
model is ever written to disk, and Results/model.joblib is never overwritten.

Stage 1 groups are provisional CANDIDATE PROFILES inferred from recorded position
and time proximity -- never verified fishing tows or casts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from shelfcast import model, reveal
from shelfcast.config import (
    DEFAULT_DEPTH_GRID,
    SPREAD_SCORE_DEPTHS,
    SPREAD_SEEDS,
)

# The source columns fit_model needs from the training / revealed frames.
FIT_SOURCE_COLUMNS = ["latitude", "longitude", "depth_m", "time", "temperature_c"]


def _profile_ids(train_df: pd.DataFrame) -> np.ndarray:
    """Distinct candidate profile ids present in the training frame."""
    if "profile_id" not in train_df.columns:
        raise ValueError("training frame is missing the 'profile_id' column")
    return np.sort(train_df["profile_id"].unique())


def resample_profiles(train_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return a profile-level bootstrap resample of the training rows.

    Samples WHOLE candidate profile ids WITH replacement and includes every
    reading of each sampled profile, so no individual reading is ever sampled on
    its own and no partial profile can appear (Req 1.1, 1.2). Deterministic for a
    given (train_df, seed) via a seeded numpy Generator. Requires at least two
    distinct profile ids, else raises ValueError (Req 1.5).
    """
    ids = _profile_ids(train_df)
    if len(ids) < 2:
        raise ValueError(
            "spread resampling needs at least 2 distinct candidate profile ids; "
            f"found {len(ids)}"
        )
    rng = np.random.default_rng(seed)
    chosen = rng.choice(ids, size=len(ids), replace=True)
    # Include the full set of rows for each sampled profile (whole profiles).
    groups = {pid: group for pid, group in train_df.groupby("profile_id")}
    parts = [groups[pid] for pid in chosen]
    return pd.concat(parts, ignore_index=True)


def fit_spread_models(
    train_df: pd.DataFrame,
    revealed_df: pd.DataFrame | None = None,
    seeds: list[int] = SPREAD_SEEDS,
) -> list:
    """Fit exactly len(seeds) (five) reproducible spread models.

    For each declared seed, build a profile-level resample of the training rows
    and fit it with shelfcast.model.fit_model unchanged. When revealed_df is
    given, ONLY that one selected revealed profile's rows are appended to every
    resample, so every updated model includes the revealed profile and no other
    hidden profile enters the fit (Req 6.1, 6.4). Models are held in memory only
    and are NEVER written to disk; Results/model.joblib is untouched (Req 1.6,
    6.3). Raises ValueError when the training frame has fewer than two profile
    ids (Req 1.5).
    """
    models = []
    revealed_rows = revealed_df[FIT_SOURCE_COLUMNS] if revealed_df is not None else None
    for seed in seeds:
        resampled = resample_profiles(train_df, seed)
        combined = resampled[FIT_SOURCE_COLUMNS]
        if revealed_rows is not None:
            combined = pd.concat([combined, revealed_rows], ignore_index=True)
        models.append(model.fit_model(combined))
    return models


def _as_utc_datetime(start_time):
    """Coerce a start-time value to a timezone-aware UTC datetime.

    predict_temperatures requires an aware UTC datetime. Candidate-site tables
    carry start_time as a string, while model.lookup_candidate_site returns a
    datetime; accept either here.
    """
    return pd.to_datetime(start_time, utc=True).to_pydatetime()


def _predict_across(models: list, lat, lon, start_time, depths) -> np.ndarray:
    """Matrix of predictions [n_models, n_depths] via the unchanged predictor."""
    utc_time = _as_utc_datetime(start_time)
    rows = [
        model.predict_temperatures(m, lat, lon, utc_time, list(depths)) for m in models
    ]
    return np.asarray(rows, dtype=float)


def spread_table(
    models: list, site: dict, depths: list[float] = DEFAULT_DEPTH_GRID
) -> pd.DataFrame:
    """Per-depth min/max/mean predicted temperature across the five models.

    Uses the site's recorded coordinates and recorded UTC start time and the
    unchanged shelfcast.model.predict_temperatures (Req 2.1, 2.5). Returns a
    DataFrame with columns [depth_m, temp_min, temp_max, temp_mean], one row per
    requested prediction level, in the order of `depths`. Predictions only -- no
    heldout value is read. The depths are REQUESTED PREDICTION LEVELS only; they
    do not establish the actual bottom depth at a site.
    """
    preds = _predict_across(
        models, site["latitude"], site["longitude"], site["start_time"], depths
    )
    return pd.DataFrame(
        {
            "depth_m": [float(d) for d in depths],
            "temp_min": preds.min(axis=0),
            "temp_max": preds.max(axis=0),
            "temp_mean": preds.mean(axis=0),
        }
    )


def disagreement_score(
    models: list,
    lat: float,
    lon: float,
    start_time,
    depths: list[float] = SPREAD_SCORE_DEPTHS,
) -> float:
    """Non-negative disagreement score at the shallow requested levels.

    Defined as the sum, over the 5 m and 10 m requested prediction levels, of the
    (max minus min) predicted temperature across the five spread models at that
    level, for the given coordinates and recorded UTC start time (Req 3.1, 3.2).
    Higher means the five models disagree more. Predictions only -- no candidate's
    hidden temperature_c/depth_m is read (Req 3.3). Reproducible for fixed models
    and coordinates/time (Req 3.4).
    """
    preds = _predict_across(models, lat, lon, start_time, depths)
    spread_per_depth = preds.max(axis=0) - preds.min(axis=0)
    return float(spread_per_depth.sum())


def eligible_candidates(
    sites_df: pd.DataFrame,
    selected_id: int,
    selected_site: dict,
    after_time,
) -> list[int]:
    """profile_ids eligible to be suggested, in ascending profile_id order.

    A candidate is eligible when it is NOT the selected site, lies at least
    reveal.MIN_NEARBY_KM (1 km) from the selected site by great-circle distance,
    and has a recorded start_time strictly after `after_time` (Req 4.1, 4.2,
    4.3). `after_time` is the selected site's recorded start_time before a reveal,
    or the revealed profile's final recorded measurement time after a reveal --
    the caller supplies the right value. Reads only the candidate-site columns
    profile_id/latitude/longitude/start_time; never opens heldout (Req 4.4).
    """
    after = pd.to_datetime(after_time, utc=True)
    out: list[int] = []
    for _, row in sites_df.iterrows():
        pid = int(row["profile_id"])
        if pid == selected_id:
            continue
        dist_km = reveal.haversine_km(
            selected_site["latitude"],
            selected_site["longitude"],
            row["latitude"],
            row["longitude"],
        )
        if dist_km < reveal.MIN_NEARBY_KM:
            continue
        start = pd.to_datetime(row["start_time"], utc=True)
        if not (start > after):
            continue
        out.append(pid)
    return sorted(out)


def suggest_candidate(
    models: list,
    sites_df: pd.DataFrame,
    selected_id: int,
    selected_site: dict,
    after_time,
) -> dict | None:
    """Return the single suggested candidate profile to TEST, or None.

    Scores each eligible candidate (eligible_candidates) by disagreement_score at
    5 m and 10 m and returns the highest-scoring one, breaking ties by lowest
    profile_id (Req 5.1). The result is {profile_id, score, latitude, longitude,
    start_time}. Returns None when no candidate is eligible (Req 5.4). Predictions
    only -- no hidden value is read for any candidate (Req 5.5). This is a profile
    to test, NOT an optimal site or an operational boat route.
    """
    eligible = eligible_candidates(sites_df, selected_id, selected_site, after_time)
    if not eligible:
        return None

    by_id = {int(r["profile_id"]): r for _, r in sites_df.iterrows()}
    best = None
    best_key = None
    for pid in eligible:
        row = by_id[pid]
        score = disagreement_score(
            models, row["latitude"], row["longitude"], row["start_time"]
        )
        # Highest score wins; ties broken by lowest profile_id. Negate score so
        # a plain min() on the key picks the highest score, lowest id.
        key = (-score, pid)
        if best_key is None or key < best_key:
            best_key = key
            best = {
                "profile_id": pid,
                "score": float(score),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "start_time": row["start_time"],
            }
    return best


__all__ = [
    "FIT_SOURCE_COLUMNS",
    "resample_profiles",
    "fit_spread_models",
    "spread_table",
    "disagreement_score",
    "eligible_candidates",
    "suggest_candidate",
]
