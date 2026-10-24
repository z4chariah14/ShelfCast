"""Stage 1 configuration constants.

Holds all named constants for the ShelfCast Stage 1 pipeline. No logic lives
here so that study parameters are explicit and consistently applied.
"""

from datetime import timedelta

# Study region bounds (inclusive) -- Requirement 1.1
LAT_MIN = 41.5
LAT_MAX = 42.5
LON_MIN = -70.5
LON_MAX = -69.5

# Retention + grouping constants -- Requirement 1.2-1.5
MIN_READINGS = 10  # Requirement 1.2
MIN_DEPTH_RANGE_M = 10  # Requirement 1.3
MAX_SPAN = timedelta(hours=1)  # Requirement 1.4
DEFAULT_GAP = timedelta(minutes=5)  # Requirement 1.5

# Valid physical coordinate bounds (global sanity bounds, distinct from study region)
VALID_LAT_MIN = -90.0
VALID_LAT_MAX = 90.0
VALID_LON_MIN = -180.0
VALID_LON_MAX = 180.0

REQUIRED_COLUMNS = ["time", "latitude", "longitude", "depth_m", "temperature_c"]
SOURCE_CSV_NAME = "data.csv"

# --------------------------------------------------------------------------
# Stage 2 chronological-split constants (additive; Stage 1 above is unchanged)
# --------------------------------------------------------------------------
from datetime import datetime, timezone

# Fixed replay cutoff -- Requirement 2.1
CUTOFF = datetime(2024, 8, 6, 0, 0, 0, tzinfo=timezone.utc)

PROCESSED_DIR = "Data/processed"  # Stage 1 outputs (Stage 2 input)
SPLITS_DIR = "Data/splits"  # Stage 2 outputs

# Candidate_Sites columns -- exactly these four, in this order (Req 4.1)
CANDIDATE_SITE_COLUMNS = ["profile_id", "latitude", "longitude", "start_time"]

# --------------------------------------------------------------------------
# Stage 3 temperature-predictor constants (additive; Stage 1 and Stage 2
# sections above are unchanged)
# --------------------------------------------------------------------------
# A fixed, declared UTC reference instant used to convert a UTC time into
# hours for the model's time feature -- Requirement 1.2
TIME_REFERENCE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# Exactly four model inputs, in fixed declared order -- Requirement 1.2
FEATURE_ORDER = ["latitude", "longitude", "depth_m", "hours_since_reference"]

# Model target column -- Requirement 1.3
TARGET_COLUMN = "temperature_c"

# Fixed, declared list of REQUESTED PREDICTION LEVELS (depths in metres at
# which a prediction is requested) used when the caller supplies no depths.
# These are requested prediction levels only; they do NOT establish or claim
# the actual bottom depth at a site -- Requirements 4.2, 4.9
DEFAULT_DEPTH_GRID = [5.0, 10.0, 20.0, 30.0, 50.0]

# Fixed random seed for reproducible fits -- Requirements 1.4, 6.1
RANDOM_STATE = 42

# Stage 3 observational data inputs (the ONLY observational files Stage 3 may
# open) -- Requirement 5.1
TRAIN_POINTS_PATH = "Data/splits/train_points.csv"
CANDIDATE_SITES_PATH = "Data/splits/candidate_sites.csv"

# Stage 3 output artifacts under Results/ -- Requirements 3.2, 3.3
RESULTS_DIR = "Results"
MODEL_PATH = "Results/model.joblib"
METADATA_PATH = "Results/model_metadata.json"

# Candidate-profile integrity note recorded in the metadata report -- Req 3.3, 7.5
CANDIDATE_PROFILE_NOTE = (
    "Groups are provisional candidate profiles inferred from recorded position "
    "and time proximity; they are NOT verified fishing tows or casts."
)

# --------------------------------------------------------------------------
# Stage 5 reveal-loop constant (additive; Stage 1-3 sections above unchanged)
# --------------------------------------------------------------------------
# Hidden heldout points. Opened ONLY by shelfcast.reveal.read_revealed_profile,
# and only after the explicit "Reveal actual measurements" click, and only for
# the selected profile_id's rows. No pre-reveal path may open this file.
HELDOUT_POINTS_PATH = "Data/splits/heldout_points.csv"

# --------------------------------------------------------------------------
# Stage 6 spread + suggestion constants (additive; Stage 1-5 sections above
# are unchanged)
# --------------------------------------------------------------------------
# Exactly five reproducible spread models. Each is fit by shelfcast.spread on a
# profile-level bootstrap resample of the training candidate profiles (whole
# profiles, never individual readings). The spread is an EXPLORATORY measure,
# NOT a calibrated confidence interval -- Requirements 1.1, 1.3, 2.4
SPREAD_N_MODELS = 5

# Fixed, declared per-model random seeds so the five spread models and their
# predictions are reproducible run to run -- Requirement 1.3
SPREAD_SEEDS = [101, 202, 303, 404, 505]

# The disagreement score is computed from the five models' predictions at these
# shallow requested prediction levels only -- Requirement 3.1
SPREAD_SCORE_DEPTHS = [5.0, 10.0]
