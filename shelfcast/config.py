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
