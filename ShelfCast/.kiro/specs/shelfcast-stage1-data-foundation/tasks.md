# Implementation Plan: ShelfCast Stage 1 Data Foundation

## Overview

Build the lean Stage 1 data pipeline exactly as specified in the design: a constants module (`shelfcast/config.py`), a single processing module (`shelfcast/pipeline.py`) holding all functions as separate well-named functions, a thin argparse CLI (`Scripts/prepare_data.py`), and two focused pytest files. Runtime code uses pandas and the standard library only — no numpy. Tasks are ordered so each stage is testable as soon as it exists, starting from constants and load, through clean/validate, region filter, grouping/retention, summary/report, output writing, the CLI, focused tests, documentation/hygiene, and a final end-to-end smoke test.

All paths are project-root-relative (project root is `ShelfCast/`); there is no nested `ShelfCast/` segment.

## Tasks

- [ ] 1. Create package skeleton and configuration constants
  - [ ] 1.1 Create `shelfcast/__init__.py` and `shelfcast/config.py`
    - Create `shelfcast/__init__.py` (empty package marker).
    - Create `shelfcast/config.py` with all named constants and no logic:
      - Study-region bounds `LAT_MIN=41.5`, `LAT_MAX=42.5`, `LON_MIN=-70.5`, `LON_MAX=-69.5`.
      - `MIN_READINGS=10`, `MIN_DEPTH_RANGE_M=10`, `MAX_SPAN=timedelta(hours=1)`, `DEFAULT_GAP=timedelta(minutes=5)`.
      - Global sanity bounds `VALID_LAT_MIN=-90.0`, `VALID_LAT_MAX=90.0`, `VALID_LON_MIN=-180.0`, `VALID_LON_MAX=180.0`.
      - `REQUIRED_COLUMNS=["time","latitude","longitude","depth_m","temperature_c"]`, `SOURCE_CSV_NAME="data.csv"`.
    - Import `timedelta` from the standard library `datetime`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 2. Implement archive loading in the pipeline module
  - [ ] 2.1 Implement `load_archive` in `shelfcast/pipeline.py`
    - Open `zip_path` with the standard library `zipfile`; raise `FileNotFoundError` when the ZIP path is absent.
    - Locate `csv_name` (default `SOURCE_CSV_NAME`) inside the archive; raise a clear `KeyError`/`ValueError` naming the missing member when `data.csv` is not present.
    - Read the CSV with pandas as RAW STRINGS: `dtype=str` with `keep_default_na=False` and `na_filter=False` so missing-value / `NaN`-like text is preserved verbatim as strings and no coercion happens at load.
    - Capture `input_count` (rows read from the CSV) for the funnel.
    - Do not dedupe, coerce, or drop at this stage.
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 2.2 Write unit tests for `load_archive`
    - Missing ZIP raises `FileNotFoundError`; archive without `data.csv` raises a clear error; present archive returns raw string frame with correct `input_count` and values preserved verbatim.
    - _Requirements: 3.1, 3.2_

- [ ] 3. Implement cleaning and validation
  - [ ] 3.1 Implement `clean_readings` in `shelfcast/pipeline.py` in strict order
    - (a) `drop_duplicates(keep="first")` across all columns on the RAW STRING rows first; capture `duplicate_count`.
    - (b) Coerce types on the deduplicated frame: `time` via `pd.to_datetime(..., utc=True, format="ISO8601", errors="coerce")`; numeric columns via `pd.to_numeric(..., errors="coerce")`.
    - (c) Classify invalid rows: missing/unparseable values surface as NaN/NaT; non-finite values including +/-inf detected using pandas only (no numpy, e.g. `isin([float("inf"), float("-inf")])` or `math.isfinite` via apply); latitude outside -90..90 inclusive; longitude outside -180..180 inclusive (using `VALID_*` bounds); negative `depth_m`.
    - (d) Temperature special case: `temperature_c` makes a row invalid only when missing, unparseable, or non-finite — a finite but unusual temperature never rejects a row.
    - Drop invalid rows as a group (a row failing multiple checks is counted once); capture `rejected_count` computed on the already-deduplicated set.
    - Return `(cleaned_df, counts)` where `counts` carries `input_count`, `duplicate_count`, `rejected_count`.
    - _Requirements: 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 4. Implement study-region filtering
  - [ ] 4.1 Implement `filter_region` in `shelfcast/pipeline.py`
    - Keep rows whose latitude and longitude fall inside the inclusive study-region bounds (`LAT_MIN..LAT_MAX`, `LON_MIN..LON_MAX`, inclusive on all four edges).
    - Return `(regional_df, regional_count)`.
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 5. Implement candidate-profile grouping and retention
  - [ ] 5.1 Implement `build_profiles` in `shelfcast/pipeline.py`
    - Partition by identical recorded `(latitude, longitude)`; process each partition independently.
    - Within a partition, sort ascending by `time`.
    - Walk ordered rows: start a new segment when the gap to the previous reading exceeds `gap_threshold` (gap split) OR when appending the next reading would make the earliest-to-latest span exceed `MAX_SPAN` (span split). On a span split, retain the earlier portion and begin a new segment starting at the overflowing reading (span check uses the segment's earliest reading).
    - Apply retention to every segment (including span-split segments): keep only if `n_readings >= MIN_READINGS` AND `depth_max - depth_min >= MIN_DEPTH_RANGE_M`.
    - Assign sequential `profile_id = 0, 1, 2, ...` in a stable order (location, then start time); attach `profile_id` to each retained reading.
    - Return `(points_df, summary_rows)`.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ] 6. Implement summary rows and report assembly
  - [ ] 6.1 Implement `build_summary_rows` and `build_report` in `shelfcast/pipeline.py`
    - `build_summary_rows`: one row per `profile_id` with `profile_id`, `latitude`, `longitude`, `start_time`, `end_time`, `n_readings`, `depth_min`, `depth_max`, `depth_range`, `temp_min`, `temp_max`, `duration`.
    - `build_report`: assemble the report dict with funnel `counts` (`input_count`, `duplicate_count`, `rejected_count`, `regional_count`, `retained_count`, `profile_count`), `grouping_rules` (gap threshold, max span, min readings, min depth range, study-region bounds), the `integrity_note` (groups are provisional candidate profiles, NOT verified tows/casts), and the `starter_zip_note` recording the `tow_id`/`segment_type` omission.
    - Use "candidate profile" wording; never emit a tow/cast/segment-type label.
    - _Requirements: 6.8, 6.9, 6.10, 7.4, 7.5_

- [ ] 7. Implement output writing
  - [ ] 7.1 Implement `write_outputs` in `shelfcast/pipeline.py`
    - Create the output directory with `os.makedirs(out_dir, exist_ok=True)`.
    - Write `profile_points.csv` (`index=False`), `profile_summary.csv` (from summary rows), and `stage1_report.json` using the stdlib `json` module with `indent=2`.
    - Handle empty results: write header-only CSVs and a report whose counts are zeroed, without crashing.
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests written so far pass, ask the user if questions arise.

- [ ] 9. Implement the command-line entry point
  - [ ] 9.1 Implement `Scripts/prepare_data.py` argparse CLI
    - Arguments: `--input` (default `Data/raw/emolt.zip`), `--output` (default `Data/processed`), `--gap-minutes` (float, overrides default gap).
    - Resolve the gap: `timedelta(minutes=args.gap_minutes)` when provided, else `DEFAULT_GAP` from the config module.
    - Orchestrate the pipeline functions in order: `load_archive` -> `clean_readings` -> `filter_region` -> `build_profiles` -> `build_report` -> `write_outputs`; thread `regional_count` and `retained_count` into the counts.
    - Catch `FileNotFoundError`, `KeyError`, `ValueError`, print a clear message to stderr, and return a non-zero exit code; return 0 on success.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 10. Write focused parsing tests
  - [ ] 10.1 Write `tests/test_parsing.py`
    - ISO 8601 `Z` timestamp (e.g. `2023-07-01T12:00:00Z`) parses to a UTC datetime.
    - Malformed timestamp coerces to `NaT` and the row is rejected.
    - Non-numeric text in a required numeric column coerces to `NaN` and the row is rejected.
    - Temperature-only exception: a finite-but-unusual temperature is retained; a missing or non-finite temperature is rejected.
    - Latitude outside -90..90 or longitude outside -180..180 is rejected.
    - Negative `depth_m` is rejected.
    - Exact raw deduplication: identical raw rows collapse to one with correct `duplicate_count`, including a case where preserved missing-value text makes two raw rows identical so they dedupe correctly.
    - _Requirements: 8.3_

- [ ] 11. Write focused grouping tests
  - [ ] 11.1 Write `tests/test_grouping.py`
    - Gap split: a consecutive gap greater than the threshold places readings on either side into different groups.
    - One-hour `MAX_SPAN` split: a run with small gaps whose total span exceeds one hour is split — the earlier portion is retained and a new group starts at the split point.
    - Retention boundaries: exactly `MIN_READINGS` is retained while one fewer is discarded; a depth range of exactly `MIN_DEPTH_RANGE_M` is retained while just under is discarded.
    - _Requirements: 8.4_

- [ ] 12. Add documentation and repository hygiene
  - [ ] 12.1 Write README, `.gitignore`, and the workspace steering file
    - `README.md`: state the EXACT run command `python Scripts/prepare_data.py` (run from the project root) and include eMOLT dataset attribution.
    - `.gitignore`: exclude `Data/processed/` outputs and `Data/raw/emolt.zip` while keeping the `.kiro/` directory tracked.
    - `.kiro/steering/` file: state the ShelfCast purpose and the Stage 1 scope limits (data pipeline + three artifacts + docs/tests only; no model, map, dashboard, or deployment).
    - _Requirements: 8.1, 8.2, 8.5_

- [ ] 13. Final smoke test - end-to-end verification
  - Run the documented CLI command `python Scripts/prepare_data.py` from the project root against `Data/raw/emolt.zip`.
  - Confirm exit code 0 and that `Data/processed/profile_points.csv`, `Data/processed/profile_summary.csv`, and `Data/processed/stage1_report.json` are written with consistent funnel counts (input -> rejected -> regional -> retained -> profile_count).
  - Run the full pytest suite and confirm it passes.
  - This task verifies end-to-end and MUST be last.
  - _Requirements: 8.6_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Each task references specific requirement clauses for traceability.
- Checkpoints ensure incremental validation; the final smoke test confirms the full funnel end-to-end.
- Runtime code uses pandas and the standard library only — no numpy. Tests may use pandas.
- The design has no "Correctness Properties" section, so no property-based tests are included; tests are focused unit/example tests for parsing and grouping.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["4.1", "5.1"] },
    { "id": 4, "tasks": ["6.1", "7.1"] },
    { "id": 5, "tasks": ["9.1", "10.1", "11.1", "12.1"] }
  ]
}
```
