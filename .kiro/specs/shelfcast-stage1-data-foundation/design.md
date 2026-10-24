# Design Document

## Overview

ShelfCast Stage 1 is a lean, command-line data pipeline that turns the released eMOLT starter archive into three reviewable artifacts: a cleaned point dataset, a candidate-profile summary, and a processing report. The pipeline is written in Python using pandas and the standard library only — there is no direct dependency on numpy in runtime code.

Scope is strictly the data foundation: load, clean/validate, region-filter, group into provisional candidate profiles, apply retention rules, and write outputs. There is no predictive model, map, dashboard, or deployment in Stage 1.

A central integrity constraint shapes the design. The released starter archive `Data/raw/emolt.zip` omits the `tow_id` and `segment_type` columns that the full eMOLT source provides. Because Stage 1 cannot see verified tow or cast boundaries, every group it produces is a *provisional candidate profile* inferred from recorded position and time proximity. The design must never present these groups as verified fishing tows or casts, and must record the omission in the report (Requirement 6.9, 6.10).

All paths in this document are relative to the project root `ShelfCast/`. The Python package lives at `shelfcast/`, the CLI entry at `Scripts/prepare_data.py`, raw input at `Data/raw/emolt.zip`, and outputs at `Data/processed/`.

## Architecture

### Module structure

The pipeline is deliberately lean: a constants module, one small pipeline module that holds all processing functions as separate well-named functions, and a thin CLI driver. The processing functions are not split across many files — they live together in `pipeline.py` so the flow is easy to read, while each remains individually callable and testable.

```
shelfcast/
  __init__.py
  config.py        # named constants (Requirement 1)
  pipeline.py      # all processing functions in one module:
                   #   load_archive        -> ZIP + CSV load, parse/coerce (Requirement 3.1-3.4)
                   #   clean_readings      -> raw dedupe + validity classification + counts (Requirements 3, 4)
                   #   filter_region       -> study-region filtering (Requirement 5)
                   #   build_profiles      -> candidate-profile grouping + retention (Requirement 6)
                   #   build_summary_rows  -> one summary row per profile (Requirement 7.2)
                   #   build_report        -> assemble report dict (Requirements 6, 7)
                   #   write_outputs       -> write CSV + JSON artifacts (Requirement 7)
Scripts/
  prepare_data.py  # argparse CLI; orchestrates pipeline functions; non-zero exit on failure (Requirement 2)
tests/
  test_parsing.py  # parsing + validation tests (Requirement 8.3)
  test_grouping.py # grouping + retention tests (Requirement 8.4)
```

Each function in `pipeline.py` takes and returns pandas objects (or plain dicts/counts), so each stage is independently testable even though they share a module. The CLI driver is the only place that performs I/O orchestration and process-exit handling.

### High-level component diagram
```
Scripts/prepare_data.py (CLI)
        |
        v
  pipeline.load_archive  --->  pipeline.clean_readings  --->  pipeline.filter_region
                                                                   |
                                                                   v
                                  pipeline.write_outputs  <---  pipeline.build_profiles
                                            ^                        |
                                            |                        v
                          pipeline.build_report / build_summary_rows
```

All boxes after the CLI are functions in the single `shelfcast/pipeline.py` module.

## Data Flow

The pipeline executes a fixed, linear sequence. Counts are captured at each boundary so the final report can describe the funnel.

1. **Load** (`load_archive`): Open `emolt.zip` with `zipfile`, locate `data.csv`, read it with pandas **as raw strings** (no type coercion yet). Capture `input_count` (rows read from the CSV). (Requirement 3.1-3.4)
2. **Clean / validate** (`clean_readings`): In strict order —
   1. **drop_duplicates on the raw string rows** (the values exactly as read from the CSV, before any `to_datetime`/`to_numeric` coercion),
   2. **coerce types** (`time` -> UTC datetime, numeric columns -> float),
   3. **classify and reject invalid values** (coerced NaN/NaT plus range checks),
   4. **count** duplicates and rejections.
   Because deduplication happens on the raw set first, `rejected_count` is computed on the already-deduplicated rows and stays accurate. (Requirement 3.5-3.12, 4.1-4.5)
3. **Region filter** (`filter_region`): Keep only rows whose latitude and longitude fall inside the inclusive study-region bounds. Capture `regional_count`. (Requirement 5.1-5.3)
4. **Group** (`build_profiles`): Group regional rows by identical recorded `(latitude, longitude)`, split on consecutive time gaps greater than the gap threshold, split on `MAX_SPAN` overflow, then apply `MIN_READINGS` and `MIN_DEPTH_RANGE_M` retention. Assign a sequential `profile_id` to each retained group. Capture `retained_count` (rows across all retained profiles) and the retained profiles themselves. (Requirement 6.1-6.9)
5. **Write** (`build_summary_rows` + `build_report` + `write_outputs`): Build `profile_summary` rows and the report dict, then write `profile_points.csv`, `profile_summary.csv`, and `stage1_report.json` to the output directory. (Requirement 7.1-7.5)

The flow is `load (raw) → drop_duplicates (raw) → coerce types → classify/reject → region filter → group → retain → write`. Each arrow carries a DataFrame plus accumulated counts; no stage reaches backward.

## Components and Interfaces

### `shelfcast/config.py` (Requirement 1)

Holds all Stage 1 constants as module-level names. No logic.

```python
from datetime import timedelta

# Study region bounds (inclusive) — Requirement 1.1
LAT_MIN = 41.5
LAT_MAX = 42.5
LON_MIN = -70.5
LON_MAX = -69.5

# Retention + grouping constants — Requirement 1.2–1.5
MIN_READINGS = 10                       # Requirement 1.2
MIN_DEPTH_RANGE_M = 10                   # Requirement 1.3
MAX_SPAN = timedelta(hours=1)            # Requirement 1.4
DEFAULT_GAP = timedelta(minutes=5)       # Requirement 1.5

# Valid physical coordinate bounds (global sanity bounds, distinct from study region)
VALID_LAT_MIN = -90.0
VALID_LAT_MAX = 90.0
VALID_LON_MIN = -180.0
VALID_LON_MAX = 180.0

REQUIRED_COLUMNS = ["time", "latitude", "longitude", "depth_m", "temperature_c"]
SOURCE_CSV_NAME = "data.csv"
```

All pipeline functions import these names rather than hard-coding values, satisfying Requirement 1.6.

### `shelfcast/pipeline.py`

A single module containing all processing functions. Each is a focused function that can be imported and tested on its own. Runtime code uses pandas and the standard library only; it does **not** import numpy.

#### `load_archive` (Requirement 3.1-3.4)

```python
def load_archive(zip_path: str, csv_name: str = SOURCE_CSV_NAME) -> pd.DataFrame:
    """Open the ZIP with zipfile, read csv_name with pandas as raw strings.

    Reads every column with dtype=str (no type inference) so the raw CSV values
    are preserved verbatim for exact deduplication downstream. Type coercion is
    deferred to clean_readings. Returns the raw string frame.

    Raises FileNotFoundError if zip_path is absent (Error Handling).
    Raises a clear error (KeyError/ValueError) if csv_name is not in the archive.
    """
```

Load does not coerce types, dedupe, or drop anything; it only reads raw strings and records `input_count`. Keeping coercion out of load is what lets `clean_readings` deduplicate the original raw values first.

#### `clean_readings` (Requirement 3.5-3.12, 4)

```python
def clean_readings(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Dedupe raw rows, coerce types, classify validity, drop invalid rows.

    Returns (cleaned_df, counts) where counts includes:
      - input_count      : rows received (post-load)
      - duplicate_count  : exact-duplicate raw rows removed
      - rejected_count   : invalid rows removed (post-dedup, post-coercion)
    """
```

Processing order (this exact order matters):

1. **Dedupe raw rows first.** `df.drop_duplicates(keep="first")` across all columns while the values are still the raw strings read from the CSV — before any `to_datetime`/`to_numeric` coercion. Record `duplicate_count`. Deduplicating the original raw text (rather than coerced values) guarantees rejection counts are computed on the already-deduplicated set and stay accurate. (Requirement 3.6)
2. **Coerce types** on the deduplicated frame:
   - `time`: `pd.to_datetime(series, utc=True, format="ISO8601", errors="coerce")` so a trailing `Z` is honored and unparseable values become `NaT`. (Requirement 3.3)
   - numeric columns: `pd.to_numeric(series, errors="coerce")` so non-numeric text becomes `NaN`. (Requirement 3.4)
3. **Classify and reject invalid values.** A row is *invalid* if any of:
   - a required value is missing (NaN/NaT after coercion). (Requirement 3.7, 4.1)
   - a required value was unparseable (also surfaces as NaN/NaT). (Requirement 3.8)
   - a numeric value is non-finite (NaN or ±inf). (Requirement 3.9)
   - `latitude` is outside −90..90 inclusive, or `longitude` outside −180..180 inclusive (using `VALID_*` bounds). (Requirement 3.10)
   - `depth_m` is negative. (Requirement 3.11)
4. **Temperature special case**: `temperature_c` makes a row invalid *only* when it is missing, unparseable, or non-finite. A valid-but-unusual (but finite) temperature value never rejects a row. (Requirement 3.12, 4.3)
5. **Drop** invalid rows and count them as `rejected_count`. Invalid rows are removed as a group so a row failing multiple checks is counted once. (Requirement 4.4, 4.5)

**Non-finite detection without numpy.** After `pd.to_numeric(..., errors="coerce")`, non-numeric text is already `NaN`. Missing values are detected with `Series.isna()`. Infinities are detected with pandas only — e.g. `series.isin([float("inf"), float("-inf")])` (or by replacing `float("inf")`/`float("-inf")` with NA and then testing `isna()`); `math.isfinite` via `Series.apply` may be used if a per-element check is clearer. No numpy import is required.

#### `filter_region` (Requirement 5)

```python
def filter_region(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep rows inside the inclusive study region; return (regional_df, regional_count)."""
    mask = (
        (df["latitude"] >= LAT_MIN) & (df["latitude"] <= LAT_MAX) &
        (df["longitude"] >= LON_MIN) & (df["longitude"] <= LON_MAX)
    )
    regional = df[mask]
    return regional, len(regional)
```

Bounds are inclusive on all four edges (Requirement 5.1). Rows outside are excluded from grouping (Requirement 5.2); the count is reported (Requirement 5.3).

#### `build_profiles` (Requirement 6)

```python
def build_profiles(df: pd.DataFrame, gap_threshold: timedelta) -> tuple[pd.DataFrame, list[dict]]:
    """Group regional readings into retained candidate profiles.

    Returns (points_df, summary_rows) where points_df is every retained reading with
    a 'profile_id' column, and summary_rows is one dict per retained profile.
    """
```

See the Grouping Algorithm section for the step-by-step procedure.

#### `build_summary_rows` / `build_report` (Requirement 6.8, 6.10, 7.4, 7.5)

```python
def build_summary_rows(points_df: pd.DataFrame) -> list[dict]:
    """One summary row per profile_id (see Profile_Summary schema)."""

def build_report(counts: dict, n_profiles: int, gap_threshold: timedelta) -> dict:
    """Assemble the stage1_report.json dict: counts, grouping rules, and the
    starter-ZIP omission note (tow_id / segment_type)."""
```

#### `write_outputs` (Requirement 7.1-7.3)

```python
def write_outputs(out_dir: str, points_df: pd.DataFrame,
                  summary_rows: list[dict], report: dict) -> None:
    """Create out_dir if needed, then write:
      - profile_points.csv   (points_df.to_csv, index=False)
      - profile_summary.csv  (from summary_rows)
      - stage1_report.json   (json.dump, indent=2)
    """
```

### `Scripts/prepare_data.py` (Requirement 2)

```python
from shelfcast import pipeline
from shelfcast.config import DEFAULT_GAP

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ShelfCast Stage 1 data pipeline")
    parser.add_argument("--input", default="Data/raw/emolt.zip")      # Req 2.1
    parser.add_argument("--output", default="Data/processed")          # Req 2.2
    parser.add_argument("--gap-minutes", type=float, default=None)     # Req 2.3
    args = parser.parse_args(argv)

    gap = (timedelta(minutes=args.gap_minutes)
           if args.gap_minutes is not None else DEFAULT_GAP)           # Req 2.4

    try:
        raw = pipeline.load_archive(args.input)
        cleaned, counts = pipeline.clean_readings(raw)
        regional, counts["regional_count"] = pipeline.filter_region(cleaned)
        points, summary = pipeline.build_profiles(regional, gap)
        counts["retained_count"] = len(points)
        report = pipeline.build_report(counts, n_profiles=len(summary),
                                       gap_threshold=gap)
        pipeline.write_outputs(args.output, points, summary, report)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Stage 1 failed: {exc}", file=sys.stderr)
        return 1                                                       # non-zero on failure
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

The CLI is intentionally thin: argument parsing, gap resolution (Requirement 2.4), orchestration of the pipeline functions (Requirement 2.5), and a non-zero exit on failure.

## Data Models

### Source_CSV (input, inside `emolt.zip`)

| Column | Type | Notes |
|---|---|---|
| `time` | string | UTC ISO 8601 with trailing `Z` |
| `latitude` | number | decimal degrees |
| `longitude` | number | decimal degrees |
| `depth_m` | number | meters, non-negative |
| `temperature_c` | number | degrees Celsius |

The starter archive omits `tow_id` and `segment_type`; Stage 1 does not read them and never emits them.

### `profile_points.csv` (Requirement 7.1)

All original reading columns plus the assigned profile id. One row per retained reading.

| Column | Type | Description |
|---|---|---|
| `time` | ISO 8601 UTC | reading timestamp |
| `latitude` | float | recorded latitude |
| `longitude` | float | recorded longitude |
| `depth_m` | float | depth in meters |
| `temperature_c` | float | temperature in °C |
| `profile_id` | int | id of the retained candidate profile this reading belongs to |

### `profile_summary.csv` (Requirement 7.2)

One row per retained candidate profile.

| Column | Type | Description |
|---|---|---|
| `profile_id` | int | sequential unique id |
| `latitude` | float | shared recorded latitude of the group |
| `longitude` | float | shared recorded longitude of the group |
| `start_time` | ISO 8601 UTC | earliest reading timestamp in the profile |
| `end_time` | ISO 8601 UTC | latest reading timestamp in the profile |
| `n_readings` | int | number of readings in the profile (≥ MIN_READINGS) |
| `depth_min` | float | minimum depth in the profile |
| `depth_max` | float | maximum depth in the profile |
| `depth_range` | float | depth_max − depth_min (≥ MIN_DEPTH_RANGE_M) |
| `temp_min` | float | minimum temperature in the profile |
| `temp_max` | float | maximum temperature in the profile |
| `duration` | string/seconds | end_time − start_time (≤ MAX_SPAN) |

### `stage1_report.json` (Requirement 7.3-7.5, 6.8, 6.10)

```json
{
  "counts": {
    "input_count": 0,
    "duplicate_count": 0,
    "rejected_count": 0,
    "regional_count": 0,
    "retained_count": 0,
    "profile_count": 0
  },
  "grouping_rules": {
    "gap_threshold_minutes": 5,
    "max_span_minutes": 60,
    "min_readings": 10,
    "min_depth_range_m": 10,
    "study_region": {
      "lat_min": 41.5, "lat_max": 42.5,
      "lon_min": -70.5, "lon_max": -69.5
    }
  },
  "integrity_note": "Groups are provisional candidate profiles inferred from recorded position and time proximity; they are NOT verified fishing tows or casts.",
  "starter_zip_note": "The released starter ZIP (Data/raw/emolt.zip) omits the tow_id and segment_type columns that the full eMOLT source provides. Stage 1 does not use them and omits any tow/cast/segment-type label from its outputs."
}
```

The report carries the funnel counts (Requirement 7.4), the grouping rules applied (Requirement 7.5, 6.8), and the explicit starter-ZIP omission note (Requirement 6.10).

## Grouping Algorithm (Requirement 6)

Given the regional DataFrame and a `gap_threshold`:

1. **Partition by location** (Requirement 6.1). Group rows by the exact recorded `(latitude, longitude)` pair. Each location partition is processed independently.
2. **Order by time**. Within a location partition, sort rows ascending by `time`.
3. **Split on gaps** (Requirement 6.2). Walk the ordered rows. Start a new segment whenever the time difference between the current reading and the previous reading exceeds `gap_threshold`.
4. **Split on span overflow** (Requirement 6.5). While building a segment, before appending the next reading, check whether appending it would make the span (latest − earliest in the segment) exceed `MAX_SPAN`. If it would, close the current segment (retain the earlier portion as its own candidate group) and begin a new segment starting at that next reading. The gap check and the span check are both evaluated as readings are consumed; either one can start a new segment.
5. **Apply retention to every segment** (Requirement 6.3, 6.4, 6.6). For each segment produced by step 3 or step 4, keep it only if both hold:
   - `n_readings >= MIN_READINGS`, and
   - `depth_max − depth_min >= MIN_DEPTH_RANGE_M`.
   Segments failing either rule are discarded. Segments created by a span split are subject to exactly the same rules (Requirement 6.6).
6. **Assign ids** (Requirement 6.7). Number retained candidate profiles sequentially as `profile_id = 0, 1, 2, ...` in a stable order (location, then start time). Attach `profile_id` to each retained reading and emit a summary row per profile.

Pseudocode for the per-partition segmentation (steps 3–4):

```python
segments, current = [], []
for row in ordered_rows:
    if not current:
        current = [row]
        continue
    gap_break = (row.time - current[-1].time) > gap_threshold
    span_break = (row.time - current[0].time) > MAX_SPAN
    if gap_break or span_break:
        segments.append(current)   # retain earlier portion
        current = [row]            # new segment starts at this row
    else:
        current.append(row)
if current:
    segments.append(current)
# retention (step 5) is applied to every segment in `segments`
```

Note the span check uses `current[0].time` (the segment's earliest reading), so the test is whether *adding* this reading would push the earliest-to-latest span past `MAX_SPAN`; if so the reading opens a new segment and the earlier portion is retained (Requirement 6.5).

## Integrity and Scope Note

Stage 1 outputs are deliberately conservative. Every emitted group is a **provisional candidate profile**, inferred only from identical recorded position and from time proximity under the gap and span rules. Because the released starter archive omits `tow_id` and `segment_type` (columns the full eMOLT source includes), Stage 1 has no ground-truth tow or cast boundaries to validate against. Therefore:

- Output artifacts contain no `tow_id`, no cast identifier, and no `segment_type` label (Requirement 6.10).
- Summary and report wording uses "candidate profile," never "tow" or "cast" (Requirement 6.9).
- The report records the omission explicitly so downstream consumers understand the provenance (Requirement 6.10).

Scope is limited to the data pipeline, its three output artifacts, documentation (README, `.gitignore`, steering), and focused tests. No model, map, dashboard, or deployment is part of Stage 1.

## Error Handling

| Condition | Handling | Requirement |
|---|---|---|
| Missing ZIP (`input` path absent) | `load_archive` raises `FileNotFoundError`; CLI prints a clear message to stderr and returns exit code 1 | 2.5, Error Handling |
| `data.csv` not inside the archive | `load_archive` raises a clear `KeyError`/`ValueError` naming the missing member; CLI exits non-zero | 3.1 |
| Unparseable timestamp or numeric cell | Coerced to `NaT`/`NaN` in `clean_readings`, classified invalid, excluded and counted in `rejected_count` — never raises | 3.5, 3.8, 4.4 |
| All readings rejected / empty region | Pipeline still completes: writes empty `profile_points.csv`/`profile_summary.csv` (headers only) and a report whose counts reflect zeros; no crash | 5.3, 7.3 |
| No groups meet retention | Empty points/summary files plus a report with `profile_count = 0` | 6.3, 6.4 |
| Output directory missing | `write_outputs` creates it with `os.makedirs(out_dir, exist_ok=True)` | 7.1–7.3 |

The CLI maps expected failures (`FileNotFoundError`, `KeyError`, `ValueError`) to a stderr message and a non-zero exit so operators get a clear signal; unexpected exceptions propagate (also non-zero).

## Testing Strategy

Tests use `pytest` and run as single executions (no watch mode). They are a focused handful of concrete example tests — no property-based testing and no hypothesis requirement. Tests may use pandas; runtime code still avoids numpy. The two areas where logic can silently go wrong are parsing/validation and grouping, so the tests concentrate there.

### Parsing tests — `tests/test_parsing.py` (Requirement 8.3)

- **ISO 8601 `Z` timestamp**: a timestamp like `2023-07-01T12:00:00Z` parses to a UTC datetime.
- **Malformed timestamp rejected**: a row whose `time` is malformed coerces to `NaT` and is rejected.
- **Non-numeric value rejected**: a row with non-numeric text in a required numeric column coerces to `NaN` and is rejected.
- **Temperature-only exception**: a row with an unusual-but-finite temperature is retained; a row whose temperature is missing or non-finite is rejected (Requirement 3.12).
- **Invalid lat/lon rejected**: a row with latitude outside −90..90 or longitude outside −180..180 is rejected.
- **Negative depth rejected**: a row with a negative `depth_m` is rejected.
- **Exact raw deduplication**: two identical raw CSV rows collapse to one and `duplicate_count` equals the number removed.

### Grouping tests — `tests/test_grouping.py` (Requirement 8.4)

- **Gap split** (Requirement 6.2): a consecutive gap greater than the threshold starts a new group; readings on either side of the gap land in different groups.
- **One-hour (MAX_SPAN) split** (Requirement 6.5): a run at one location with small gaps whose total span exceeds one hour is split — the earlier portion is retained and a new group starts at the split point.
- **Retention boundaries** (Requirement 6.3, 6.4):
  - exactly `MIN_READINGS` readings is retained; one fewer (`MIN_READINGS − 1`) is discarded.
  - a depth range of exactly `MIN_DEPTH_RANGE_M` is retained; just under is discarded.

These concrete tests cover the parsing/validation rules and the two split behaviors plus the inclusive retention boundaries, which together exercise the Stage 1 logic that is most error-prone.
