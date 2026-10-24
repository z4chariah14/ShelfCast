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
MIN_READINGS = 10                   # Requirement 1.2
MIN_DEPTH_RANGE_M = 10              # Requirement 1.3
MAX_SPAN = timedelta(hours=1)       # Requirement 1.4
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

PROCESSED_DIR = "Data/processed"      # Stage 1 outputs (Stage 2 input)
SPLITS_DIR = "Data/splits"            # Stage 2 outputs

# Candidate_Sites columns -- exactly these four, in this order (Req 4.1)
CANDIDATE_SITE_COLUMNS = ["profile_id", "latitude", "longitude", "start_time"]
