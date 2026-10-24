"""ShelfCast Stage 4 viewer helpers.

App-only logic for the local Streamlit viewer (`app.py`), kept out of the UI so
it is importable and testable without launching Streamlit. Every function here
is a thin, read-only helper over the existing Stage 3 artifacts.

Data boundary (carried forward unchanged from Stage 3): this module references
only the training points, the candidate-site table, and the model artifacts
written under Results/. It never opens Data/splits/heldout_points.csv or
Data/processed/profile_summary.csv, and the `usecols` whitelists mean even the
allowed files never surface a hidden temperature/depth column.

Prediction reuses shelfcast.model.predict_temperatures verbatim, so the viewer's
charted values are identical to the Stage 3 prediction CLI's.

Stage 1 groups are provisional CANDIDATE PROFILES inferred from recorded
position and time proximity -- never verified fishing tows or casts.
"""

from __future__ import annotations

import pandas as pd

from shelfcast import model
from shelfcast.config import (
    CANDIDATE_SITES_PATH,
    METADATA_PATH,
    MODEL_PATH,
    TRAIN_POINTS_PATH,
)

# Only these columns may be read from the candidate-sites table (matches the
# Stage 3 lookup whitelist) -- Req 6.3.
CANDIDATE_COLUMNS = ["profile_id", "latitude", "longitude", "start_time"]

# Only recorded coordinates are read for the map layer; no hidden column -- Req 6.2.
TRAIN_LOCATION_COLUMNS = ["latitude", "longitude"]


def load_metadata(path: str = METADATA_PATH) -> dict:
    """Return the Stage 3 Model_Metadata as a dict.

    Loading a previously written metadata artifact is not an observational data
    input and is permitted under the data boundary. Raises FileNotFoundError if
    the artifact is absent so the UI can guide the user to train first.
    """
    import json

    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_fitted_model(path: str = MODEL_PATH):
    """Load the Saved_Model via the Stage 3 loader.

    Raises FileNotFoundError if the artifact is absent (so app.py can show
    guidance to run the training script).
    """
    import os

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"model artifact not found: {path} (run Scripts/train_model.py first)"
        )
    return model.load_model(path)


def load_training_locations(path: str = TRAIN_POINTS_PATH) -> pd.DataFrame:
    """Return recorded training [latitude, longitude] pairs for the map layer.

    Reads ONLY latitude and longitude via usecols, so no temperature or depth
    value is ever materialized (Req 6.2).
    """
    return pd.read_csv(path, usecols=TRAIN_LOCATION_COLUMNS)


def load_candidate_sites(path: str = CANDIDATE_SITES_PATH) -> pd.DataFrame:
    """Return candidate sites with only the four allowed columns.

    Reads ONLY [profile_id, latitude, longitude, start_time] (Req 6.3), matching
    the Stage 3 candidate-site whitelist.
    """
    return pd.read_csv(path, usecols=CANDIDATE_COLUMNS)


def predict_site_table(model_obj, site: dict, depths: list[float]) -> pd.DataFrame:
    """Return a depth_m/temperature_c table for one candidate site.

    Reuses shelfcast.model.predict_temperatures verbatim (guaranteeing parity
    with the Stage 3 CLI). `site` is the dict returned by
    model.lookup_candidate_site: {latitude, longitude, start_time}. Returns one
    row per requested depth, in the same order as `depths`. Opens no file.

    The requested depths are REQUESTED PREDICTION LEVELS only; they do not
    establish the actual bottom depth at a site.
    """
    temps = model.predict_temperatures(
        model_obj,
        site["latitude"],
        site["longitude"],
        site["start_time"],
        list(depths),
    )
    return pd.DataFrame(
        {
            "depth_m": [float(d) for d in depths],
            "temperature_c": [float(t) for t in temps],
        }
    )


__all__ = [
    "load_metadata",
    "load_fitted_model",
    "load_training_locations",
    "load_candidate_sites",
    "predict_site_table",
]
