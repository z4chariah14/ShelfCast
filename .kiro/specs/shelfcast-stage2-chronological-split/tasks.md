# Implementation Plan: ShelfCast Stage 2 Chronological Split

## Overview

Build the Stage 2 chronological replay split on top of the Stage 1 data foundation, exactly as specified in the design. Work proceeds additively: append Stage 2 constants to `shelfcast/config.py` without touching any Stage 1 constant or any Stage 1 behavior, implement all split logic as separate well-named functions in a single testable module (`shelfcast/split.py`), wire a thin argparse CLI (`Scripts/split_replay.py`) that mirrors `Scripts/prepare_data.py`, add required pytest coverage for the boundary and leakage behaviors, and update documentation and repository hygiene. Runtime and test code use pandas and the Python standard library only — no numpy.

The failure guarantee relies on ordering, not a transaction: `check_integrity` runs all integrity checks first and raises before `write_split_outputs` is ever called, so on failure nothing is written and the process exits non-zero. The design has no "Correctness Properties" section (it uses a focused example-based testing strategy), so no property-based tests are included. Because the user requires boundary and leakage coverage, the Stage 2 tests are REQUIRED (not optional). Stage 1 code is left unchanged. A separate bookkeeping task marks verifiably-complete Stage 1 task boxes. The final task verifies end-to-end and MUST be last.

All paths are project-root-relative (project root is `ShelfCast/`).

## Tasks

- [x] 1. Append additive Stage 2 constants to `shelfcast/config.py`
  - Append a clearly delimited Stage 2 block to `shelfcast/config.py`. The change is strictly additive: all existing Stage 1 constants and all Stage 1 behavior (`shelfcast/config.py`, `shelfcast/pipeline.py`, `Scripts/prepare_data.py`) stay exactly as-is; no existing Stage 1 constant or line is modified.
  - Import `datetime` and `timezone` from the stdlib `datetime`.
  - Define `CUTOFF = datetime(2024, 8, 6, 0, 0, 0, tzinfo=timezone.utc)`.
  - Define `PROCESSED_DIR = "Data/processed"` and `SPLITS_DIR = "Data/splits"`.
  - Define `CANDIDATE_SITE_COLUMNS = ["profile_id", "latitude", "longitude", "start_time"]` (exactly these four, in this order).
  - _Requirements: 1.3, 2.1, 4.1_

- [x] 2. Implement the Stage 2 split module `shelfcast/split.py`
  - [x] 2.1 Implement `load_stage1_outputs` and module scaffolding
    - Add `from __future__ import annotations`; import `json`, `os`, `pandas as pd`, and the Stage 2 config constants.
    - Define `POINT_COLUMNS = ["time", "latitude", "longitude", "depth_m", "temperature_c", "profile_id"]`.
    - `load_stage1_outputs(processed_dir)`: read `profile_summary.csv` and `profile_points.csv`; raise `FileNotFoundError` naming the missing path when either file is absent; parse summary `start_time`/`end_time` and points `time` with `pd.to_datetime(..., utc=True)`; return `(summary_df, points_df)`.
    - _Requirements: 1.1, 1.2_

  - [x] 2.2 Implement `classify_profiles`
    - Return a frame with one row per `profile_id` plus `start_time`, `end_time`, and a `label` column.
    - Label whole profiles: `end_time < cutoff` -> `train`; `start_time >= cutoff` -> `heldout`; otherwise (`start_time < cutoff <= end_time`, includes `end_time == cutoff`) -> `excluded`.
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.3 Implement `IntegrityError` and `check_integrity`
    - Define `class IntegrityError(ValueError)` so the CLI's `ValueError` catch also catches it while keeping the name explicit.
    - Signature: `check_integrity(summary_df, points_df, classification, train_points, heldout_points)`. Run ALL of the following checks in order and raise `IntegrityError` on the first failure, before any file is written (Req 6.1).
    - Check (a): summary `profile_id` set must equal points `profile_id` set, else raise naming `only_in_summary` / `only_in_points` (Req 6.2).
    - Check (b): no `profile_id` may appear more than once in `summary_df`, else raise naming the duplicated ids (Req 6.3).
    - Check (c): for every `profile_id`, summary `start_time` must equal the earliest points `time` and summary `end_time` must equal the latest points `time` for that profile (tz-aware comparison via a `groupby("profile_id")["time"].agg(["min","max"])`), else raise naming the offending ids (Req 6.4).
    - Check (d): the `train` and `heldout` `profile_id` sets (from `classification`) must be disjoint, else raise naming the overlap (Req 6.6).
    - Check (e): id-based membership — every `train_points` row must carry a `train` `profile_id` and every `heldout_points` row must carry a `heldout` `profile_id`, else raise naming the offending ids (Req 6.5). This is an id-set check, never a comparison of measured values.
    - All checks complete before any write; on failure nothing is written and the caller exits non-zero (ordering guarantee, not a transaction).
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 2.4 Implement `build_candidate_sites`
    - Select heldout profiles from the summary and project onto `CANDIDATE_SITE_COLUMNS` so `end_time`, temperature, depth, and all other summary columns are dropped by construction; `reset_index(drop=True)`.
    - This is the structural column guard: the resulting frame carries exactly `profile_id, latitude, longitude, start_time` (Req 6.7).
    - _Requirements: 4.1, 4.2, 4.3, 6.7, 10.2_

  - [x] 2.5 Implement `build_split_report`
    - Merge points to classification on `profile_id` to count points per set.
    - For each of `train` / `heldout` / `excluded`: record `profile_count`, `point_count`, and a `time_range` `{start_min, end_max}` (both `null` when the set is empty).
    - Record `cutoff` as `cutoff.isoformat()`; record `excluded_profiles` as a list of `{profile_id, start_time, end_time}` (ISO strings); include the provisional-candidate `integrity_note` (candidate profiles, NOT verified tows/casts).
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 10.1, 10.2_

  - [x] 2.6 Implement `write_split_outputs` and `_write_points`
    - Final structural candidate-sites column guard (Req 6.7) before any write: raise `IntegrityError` if `candidate_sites` columns are not exactly `CANDIDATE_SITE_COLUMNS`, or if any forbidden column is present (`temperature_c`, `temp_*`, `depth_m`, `depth_*`, `end_time`, or any summary measurement column).
    - Create `splits_dir` with `os.makedirs(..., exist_ok=True)`; write `train_points.csv`, `heldout_points.csv`, `candidate_sites.csv` (`index=False`), and `split_report.json` via stdlib `json` with `indent=2`.
    - `_write_points(path, points)`: serialize `time` as ISO 8601 for non-empty frames; write a header-only CSV using `POINT_COLUMNS` when the set is empty.
    - _Requirements: 3.1, 3.2, 5.1, 6.7, 6.8_

- [x] 3. Checkpoint - Ensure the split module behaves as designed
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement the command-line entry point `Scripts/split_replay.py`
  - [x] 4.1 Implement the thin argparse CLI
    - Mirror `Scripts/prepare_data.py`: insert the project root on `sys.path`, then import `split` and the config constants (`PROCESSED_DIR`, `SPLITS_DIR`, `CUTOFF`). Reference `split.POINT_COLUMNS` for the point-frame projection.
    - Arguments: `--processed` (default `PROCESSED_DIR`) and `--output` / `--splits` (dest `output`, default `SPLITS_DIR`).
    - Orchestrate in this order: `load_stage1_outputs` -> `classify_profiles` -> merge points to the classification labels and project `train_points`/`heldout_points` via `POINT_COLUMNS` -> `check_integrity(summary_df, points_df, classification, train_points, heldout_points)` BEFORE building or writing anything -> `build_candidate_sites` -> `build_split_report` -> `write_split_outputs`.
    - Catch `(FileNotFoundError, KeyError, ValueError)` (which includes `IntegrityError`), print a clear message to stderr, and `return 1`; print a one-line train/heldout/excluded count summary and `return 0` on success.
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 5. Write required Stage 2 tests `tests/test_split.py`
  - [x] 5.1 Write the focused pytest module (REQUIRED — boundary and leakage coverage is mandatory)
    - Use pytest with pandas and the Python standard library only; do NOT use numpy; insert the project root on `sys.path` as in the Stage 1 tests.
    - Cutoff boundary classification: `end_time < cutoff` -> `train`, `start_time >= cutoff` -> `heldout`, and `end_time == cutoff` exactly -> `excluded` (Req 8.2).
    - Spanning profile (`start_time < cutoff < end_time`) -> `excluded` (Req 8.3).
    - Whole-profile separation: after a full run, every `(profile_id, point)` appears in exactly one of `train_points.csv` / `heldout_points.csv` and no `profile_id` appears in both (Req 8.4).
    - ID-based membership leakage: every `profile_id` in `train_points.csv` is a Training_Set id, every `profile_id` in `heldout_points.csv` is a Heldout_Set id, and the two id sets are disjoint; identical measured temperature/depth values appearing in both files are NOT leakage and must not be asserted against (Req 8.6).
    - Candidate-sites structural columns: `candidate_sites.csv` columns are exactly `profile_id, latitude, longitude, start_time` with no `temperature_c`, `temp_*`, `depth_*`, `end_time`, or any summary measurement column (Req 8.5).
    - Duplicate-summary abort without write: a duplicated `profile_id` in `profile_summary` raises `IntegrityError` (non-zero exit) AND leaves `Data/splits/` with none of the four artifacts (verify on disk) (Req 8.7).
    - Summary/points time-mismatch abort without write: a summary `start_time`/`end_time` that does not equal the earliest/latest points `time` for that `profile_id` raises `IntegrityError` (non-zero exit) AND leaves `Data/splits/` with none of the four artifacts (Req 8.8).
    - Summary/points id-set mismatch abort without write: a `profile_id` present in summary but absent from points (and vice versa) raises `IntegrityError` AND leaves `Data/splits/` with none of the four artifacts (Req 8.6 integrity; Req 6.2).
    - Empty-set handling: an empty set writes a header-only CSV and records `null` time ranges in the report.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 6. Update documentation and repository hygiene
  - [x] 6.1 Update `.gitignore`, `README.md`, and the steering file
    - `.gitignore`: add a rule excluding `Data/splits/` while keeping `.kiro/` tracked.
    - `README.md`: add a Stage 2 section with the exact regenerate command `python Scripts/split_replay.py` and a note that outputs are provisional candidate profiles (never tows/casts).
    - `.kiro/steering/shelfcast-purpose-scope.md`: state "Stage 1 complete; Stage 2 active" while PRESERVING the provisional-candidate integrity rule (groups are candidate profiles, never tow/cast/segment-type).
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1_

- [x] 7. Mark verifiably-complete Stage 1 task boxes (bookkeeping)
  - [x] 7.1 Reconcile `.kiro/specs/shelfcast-stage1-data-foundation/tasks.md` with on-disk reality
    - Mark ONLY task boxes whose outputs verifiably exist as `[x]`: `shelfcast/config.py`, `shelfcast/pipeline.py` (`load_archive`, `clean_readings`, `filter_region`, `build_profiles`, `build_summary_rows`, `build_report`, `write_outputs`), `Scripts/prepare_data.py`, `tests/test_parsing.py`, `tests/test_grouping.py`, `README.md`, `.gitignore`, the steering file, and the three `Data/processed/` artifacts.
    - Leave any box unchecked whose artifact cannot be verified on disk. Do NOT rewrite or alter Stage 1 logic — this is bookkeeping only.
    - _Requirements: 1.3_

- [x] 8. Final verification - end-to-end (MUST be last)
  - Run `python -m pytest` from the project root and confirm the full suite passes.
  - Run the documented Stage 2 CLI `python Scripts/split_replay.py` from the project root; confirm exit code 0.
  - Confirm the four `Data/splits/` artifacts (`train_points.csv`, `heldout_points.csv`, `candidate_sites.csv`, `split_report.json`) are written with counts consistent with the report (train + heldout + excluded profiles account for all Stage 1 profiles; point counts match).
  - This task verifies end-to-end and MUST be last.
  - _Requirements: 7.3, 8.1_

## Notes

- Tasks marked with `*` are optional and can be skipped; the Stage 2 tests (`tests/test_split.py`, task 5.1) are intentionally NOT optional because boundary and leakage coverage is mandatory.
- Each task references specific requirement clauses for traceability.
- The design has no "Correctness Properties" section, so no property-based tests are included; Stage 2 tests are focused example-based tests, consistent with Stage 1.
- Runtime and test code use pandas and the standard library only — no numpy.
- Stage 2 constants are appended to `shelfcast/config.py` additively; all Stage 1 constants and all Stage 1 behavior (`config.py`, `pipeline.py`, `prepare_data.py`) remain unchanged.
- Leakage is id-based, not value-based: a profile's readings must never be divided across sets, and the train/heldout id sets must stay disjoint; identical measured values in both point files are normal and are not leakage.
- All integrity checks complete before any write, so a failed run leaves `Data/splits/` untouched; on failure nothing is written and the process exits non-zero. This is an ordering guarantee, not a transaction — there is no publish or rollback step.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "7.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": 3, "tasks": ["4.1", "6.1"] },
    { "id": 4, "tasks": ["5.1"] }
  ]
}
```
