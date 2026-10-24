"""ShelfCast Stage 3 temperature predictor.

All Stage 3 logic lives in this single module as separate, well-named functions
so the flow stays easy to read while each piece is individually testable. The
module fits an ExtraTreesRegressor on the Stage 2 training candidate profiles
and reuses one prediction path for both the CLI and tests.

Data boundary (the central Stage 3 constraint): this module references only the
training points and the candidate-sites table as observational inputs, plus the
model artifacts it writes under Results/. It never opens
Data/splits/heldout_points.csv or Data/processed/profile_summary.csv.

Stage 1 groups are provisional CANDIDATE PROFILES inferred from recorded
position and time proximity -- never verified fishing tows or casts.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor

from shelfcast.config import (
    CANDIDATE_PROFILE_NOTE,
    CANDIDATE_SITES_PATH,
    FEATURE_ORDER,
    MODEL_PATH,
    RANDOM_STATE,
    TARGET_COLUMN,
    TIME_REFERENCE,
)

# The source columns required in the training frame (the fourth feature,
# hours_since_reference, is derived from "time").
REQUIRED_SOURCE_COLUMNS = ["latitude", "longitude", "depth_m", "time", TARGET_COLUMN]

# Only these columns may be read from the candidate-sites table -- Req 5.3
CANDIDATE_LOOKUP_COLUMNS = ["profile_id", "latitude", "longitude", "start_time"]


# --------------------------------------------------------------------------
# Feature construction (Requirements 1.2, 2.3)
# --------------------------------------------------------------------------
def hours_since_reference(utc_time: datetime) -> float:
    """Hours (float) from TIME_REFERENCE to utc_time.

    Requires a timezone-aware UTC datetime so the subtraction is unambiguous.
    """
    if utc_time.tzinfo is None:
        raise ValueError("utc_time must be timezone-aware UTC")
    return (utc_time - TIME_REFERENCE).total_seconds() / 3600.0


def build_feature_row(
    lat: float, lon: float, depth_m: float, utc_time: datetime
) -> list[float]:
    """Return the four features in FEATURE_ORDER for one depth.

    Order is fixed as [latitude, longitude, depth_m, hours_since_reference].
    """
    return [
        float(lat),
        float(lon),
        float(depth_m),
        hours_since_reference(utc_time),
    ]


# --------------------------------------------------------------------------
# Validation (Requirements 1.5, 1.6, 1.7) -- runs fully before any fit/write
# --------------------------------------------------------------------------
def validate_training_frame(df: pd.DataFrame) -> None:
    """Raise ValueError if the training frame is unfit for a reproducible fit.

    Fails when a required column is missing, any numeric feature/target value is
    non-numeric or non-finite (NaN / +/-inf), or any timestamp is not a valid
    UTC timestamp. Runs completely before any fit or artifact write.
    """
    missing = [c for c in REQUIRED_SOURCE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"training frame missing required column(s): {missing}")

    if len(df) == 0:
        raise ValueError("training frame contains zero rows")

    # Numeric features + target must be finite numbers.
    numeric_cols = ["latitude", "longitude", "depth_m", TARGET_COLUMN]
    for col in numeric_cols:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise ValueError(
                f"column '{col}' contains non-numeric or missing value(s)"
            )
        finite = values.map(lambda v: math.isfinite(v))
        if not finite.all():
            raise ValueError(
                f"column '{col}' contains non-finite value(s) (NaN or infinity)"
            )

    # Timestamps must parse as valid UTC instants.
    times = pd.to_datetime(df["time"], utc=True, format="ISO8601", errors="coerce")
    if times.isna().any():
        raise ValueError("column 'time' contains invalid UTC timestamp(s)")


def _feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Build the FEATURE_ORDER matrix from a validated training frame."""
    times = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    hours = (times - TIME_REFERENCE).dt.total_seconds() / 3600.0
    out = pd.DataFrame(
        {
            "latitude": df["latitude"].astype(float),
            "longitude": df["longitude"].astype(float),
            "depth_m": df["depth_m"].astype(float),
            "hours_since_reference": hours.astype(float),
        }
    )
    return out[FEATURE_ORDER]


# --------------------------------------------------------------------------
# Fit (Requirements 1.1-1.4)
# --------------------------------------------------------------------------
def fit_model(df: pd.DataFrame, random_state: int = RANDOM_STATE):
    """Validate then fit an ExtraTreesRegressor with a fixed random_state.

    Reads feature and target values only from the passed training frame. Returns
    the fitted estimator. Raises ValueError if validation fails.
    """
    validate_training_frame(df)
    features = _feature_matrix(df)
    target = pd.to_numeric(df[TARGET_COLUMN]).astype(float)
    # n_jobs=1 keeps the fit CPU-friendly and deterministic across machines.
    model = ExtraTreesRegressor(random_state=random_state, n_jobs=1)
    model.fit(features.to_numpy(), target.to_numpy())
    return model


# --------------------------------------------------------------------------
# Predict (Requirements 2.1-2.6) -- the single reusable prediction path
# --------------------------------------------------------------------------
def predict_temperatures(
    model,
    lat: float,
    lon: float,
    utc_time: datetime,
    depths: list[float],
) -> list[float]:
    """Return one finite predicted temperature per requested depth, in order.

    An empty depths list returns [] without invoking the model (Req 2.4). A
    non-empty list containing any value that is not a finite number > 0 metres
    raises ValueError without invoking the model (Req 2.5). Otherwise one feature
    row is built per depth and predictions are returned one-to-one, in the same
    order as depths (Req 2.1, 2.2, 2.3, 2.6).
    """
    if len(depths) == 0:
        return []

    invalid = [
        d
        for d in depths
        if not isinstance(d, (int, float))
        or isinstance(d, bool)
        or not math.isfinite(float(d))
        or float(d) <= 0.0
    ]
    if invalid:
        raise ValueError(
            "depths must all be finite numbers greater than 0 metres; "
            f"invalid: {invalid}"
        )

    rows = [build_feature_row(lat, lon, float(d), utc_time) for d in depths]
    preds = model.predict(rows)
    result = [float(p) for p in preds]
    for d, p in zip(depths, result):
        if not math.isfinite(p):
            raise ValueError(
                f"model returned a non-finite temperature for depth {d}"
            )
    return result


# --------------------------------------------------------------------------
# Persistence (Requirements 3.2, 5.2)
# --------------------------------------------------------------------------
def save_model(model, path: str = MODEL_PATH) -> None:
    """Serialize the fitted model with joblib (the scikit-learn standard)."""
    joblib.dump(model, path)


def load_model(path: str = MODEL_PATH):
    """Load a joblib-serialized model.

    Loading a previously saved Model_Artifact is not an observational data input
    and is permitted under the data boundary (Req 5.2).
    """
    return joblib.load(path)


# --------------------------------------------------------------------------
# Metadata (Requirement 3.3)
# --------------------------------------------------------------------------
def build_metadata(
    n_rows: int, n_candidate_profiles: int, random_state: int = RANDOM_STATE
) -> dict:
    """Assemble the Metadata_Report dict describing the fitted model."""
    return {
        "feature_order": list(FEATURE_ORDER),
        "time_reference": TIME_REFERENCE.isoformat(),
        "random_state": random_state,
        "n_rows": int(n_rows),
        "n_candidate_profiles": int(n_candidate_profiles),
        "candidate_profile_note": CANDIDATE_PROFILE_NOTE,
    }


# --------------------------------------------------------------------------
# Candidate-site lookup (Requirements 4.1, 4.5, 4.8, 5.3)
# --------------------------------------------------------------------------
def lookup_candidate_site(
    profile_id: int, path: str = CANDIDATE_SITES_PATH
) -> dict:
    """Return {latitude, longitude, start_time} for one candidate profile.

    Reads ONLY the four allowed columns from candidate_sites.csv (Req 5.3).
    Raises KeyError if the profile_id matches no row (Req 4.5); raises ValueError
    if the profile_id matches more than one row -- ambiguous (Req 4.8).
    start_time is returned as a timezone-aware UTC datetime.
    """
    sites = pd.read_csv(path, usecols=CANDIDATE_LOOKUP_COLUMNS)
    matches = sites[sites["profile_id"] == profile_id]
    if len(matches) == 0:
        raise KeyError(f"profile_id {profile_id} not found in candidate sites")
    if len(matches) > 1:
        raise ValueError(
            f"profile_id {profile_id} is ambiguous: matches "
            f"{len(matches)} rows in candidate sites"
        )
    row = matches.iloc[0]
    start_time = pd.to_datetime(row["start_time"], utc=True).to_pydatetime()
    return {
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "start_time": start_time,
    }


__all__ = [
    "hours_since_reference",
    "build_feature_row",
    "validate_training_frame",
    "fit_model",
    "predict_temperatures",
    "save_model",
    "load_model",
    "build_metadata",
    "lookup_candidate_site",
]
