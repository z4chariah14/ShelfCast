# Implementation Plan: ShelfCast Stage 3 Temperature Predictor

## Overview

Build the Stage 3 temperature predictor bottom-up so each task is independently
verifiable: config constants first, then `shelfcast/model.py` helpers (features,
validation, fit, predict, persistence, metadata, candidate lookup), then the two
CLIs, then focused example tests and one end-to-end smoke check, then the status
docs. All code references only `train_points.csv` and `candidate_sites.csv` (plus
`Results/` artifacts); `heldout_points.csv` and `profile_summary.csv` are never
opened. Groups are described only as "candidate profiles". Testing is folded into
each task — no standalone test-suite task. Stage 1/2 code and outputs stay
unchanged.

## Tasks

- [x] 1. Add Stage 3 constants to `shelfcast/config.py` (additive only)
  - Append a Stage 3 block; do not alter Stage 1/2 sections
  - Add `TIME_REFERENCE` (tz-aware UTC `datetime(2024,1,1,0,0,0,tzinfo=utc)`), `FEATURE_ORDER = ["latitude","longitude","depth_m","hours_since_reference"]`, `TARGET_COLUMN = "temperature_c"`, `DEFAULT_DEPTH_GRID = [5.0,10.0,20.0,30.0,50.0]` (requested prediction levels in metres, not actual bottom depth), `RANDOM_STATE = 42`
  - Add paths `TRAIN_POINTS_PATH`, `CANDIDATE_SITES_PATH`, `RESULTS_DIR`, `MODEL_PATH`, `METADATA_PATH`
  - Add `CANDIDATE_PROFILE_NOTE` stating groups are provisional candidate profiles inferred from recorded position and time proximity, not verified fishing tows or casts
  - _Requirements: 1.2, 1.3, 1.4, 3.2, 3.3, 4.2, 4.9, 5.1, 6.1, 7.3, 7.5_

- [x] 2. Implement `shelfcast/model.py` feature and validation helpers
  - [x] 2.1 Implement `hours_since_reference` and `build_feature_row`
    - `hours_since_reference(utc_time)` = `(utc_time - TIME_REFERENCE).total_seconds() / 3600`, requires tz-aware UTC
    - `build_feature_row(lat, lon, depth_m, utc_time)` returns exactly four floats ordered as `FEATURE_ORDER`, fourth = hours since reference
    - _Requirements: 1.2, 2.3_
  - [x]* 2.2 Write example test for `build_feature_row`
    - **Property 4: Exactly four features in declared order**
    - **Validates: Requirements 1.2, 2.3**
    - Assert length 4, order matches `FEATURE_ORDER`, fourth equals hours since `TIME_REFERENCE`
  - [x] 2.3 Implement `validate_training_frame`
    - Raise `ValueError` naming the failure if any required feature/target column is missing, any feature/target value is non-numeric or non-finite (NaN/+/-inf), or any timestamp is not a valid UTC timestamp
    - Must run fully before any fit or write
    - _Requirements: 1.5, 1.6, 1.7_
  - [x]* 2.4 Write example tests for `validate_training_frame`
    - **Property 7: Invalid input rejected, no artifact written**
    - **Validates: Requirements 1.5, 1.6, 1.7**
    - Cases: missing column, NaN, +inf, -inf, invalid UTC timestamp each raise a naming `ValueError`

- [x] 3. Implement `fit_model` in `shelfcast/model.py`
  - [x] 3.1 Implement `fit_model`
    - Call `validate_training_frame` first, then fit `ExtraTreesRegressor(random_state=RANDOM_STATE)` on `FEATURE_ORDER` -> `TARGET_COLUMN`; read inputs only from the passed training frame; raise `ValueError` on zero rows
    - Return the fitted estimator
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x]* 3.2 Write example test for fit reproducibility
    - **Property 6: Reproducibility — identical inputs produce identical outputs (fit half)**
    - **Validates: Requirements 1.4, 6.1**
    - Two fits on identical frame -> identical predictions for identical query inputs

- [x] 4. Implement `predict_temperatures` in `shelfcast/model.py`
  - [x] 4.1 Implement `predict_temperatures`
    - Empty depths -> return `[]` without invoking the model
    - Non-empty list with any value that is not a finite number > 0 metres (reject NaN/+/-inf/zero/negative) -> raise `ValueError` reporting invalid depths, do not invoke the model
    - Otherwise build one feature row per depth via `build_feature_row` and return one finite temperature per depth, order preserved one-to-one
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - [x]* 4.2 Write example test for prediction contract
    - **Property 2: One finite temperature per depth, order preserved**
    - **Validates: Requirements 2.1, 2.2, 2.6**
    - Representative lat/lon/time/depths -> same length, same order, every value finite
  - [x]* 4.3 Write example tests for empty and invalid depths (model not invoked)
    - **Property 3: Empty or invalid depths do not invoke the model**
    - **Validates: Requirements 2.4, 2.5**
    - Empty list -> `[]`; non-empty with NaN/+inf/-inf/zero/negative -> `ValueError`; use a spy to assert the model is not invoked in both cases
  - [x]* 4.4 Write example test for predict reproducibility
    - **Property 6: Reproducibility — identical inputs produce identical outputs (predict half)**
    - **Validates: Requirements 6.2**
    - Two `predict_temperatures` calls with identical inputs on one model -> identical outputs

- [x] 5. Implement `save_model`, `load_model`, and `build_metadata`
  - [x] 5.1 Implement persistence and metadata helpers
    - `save_model(model, path=MODEL_PATH)` serializes with joblib; `load_model(path=MODEL_PATH)` loads with joblib (not an observational input)
    - `build_metadata(n_rows, n_candidate_profiles, random_state=RANDOM_STATE)` returns a dict with `feature_order`, `time_reference` (ISO), `random_state`, `n_rows`, `n_candidate_profiles`, and `candidate_profile_note` from `CANDIDATE_PROFILE_NOTE`
    - _Requirements: 3.2, 3.3, 5.2_
  - [x]* 5.2 Write example test for `build_metadata`
    - Assert all required keys present, `feature_order` equals `FEATURE_ORDER`, note uses "candidate profile" wording and is not described as a tow or cast
    - _Requirements: 3.3, 7.5_

- [x] 6. Implement `lookup_candidate_site` in `shelfcast/model.py`
  - [x] 6.1 Implement `lookup_candidate_site`
    - Read `candidate_sites.csv` using ONLY columns `[profile_id, latitude, longitude, start_time]`; never reference heldout or profile_summary files
    - Return `{latitude, longitude, start_time}` (start_time tz-aware UTC) for the single matching row
    - Raise `KeyError` if no row matches; raise `ValueError` (ambiguous) if more than one row matches
    - _Requirements: 4.1, 4.5, 4.8, 5.3_
  - [x]* 6.2 Write example tests for candidate lookup
    - Known id -> row with expected lat/lon/start_time; unknown id -> `KeyError`; duplicate id -> `ValueError`; assert only the four allowed columns are read
    - _Requirements: 4.1, 4.5, 4.8, 5.3_

- [x] 7. Add `scikit-learn` and `joblib` to `requirements.txt`
  - Add pinned entries for `scikit-learn` and `joblib`; do not remove existing Stage 1/2 dependencies
  - _Requirements: 1.4, 3.2_

- [x] 8. Implement `Scripts/train_model.py` CLI
  - [x] 8.1 Implement the training CLI
    - Follow the `split_replay.py` pattern: insert project root on `sys.path`, `argparse` with `--train` (default `TRAIN_POINTS_PATH`), `--model` (default `MODEL_PATH`), `--metadata` (default `METADATA_PATH`); `main(argv=None) -> int`; `if __name__ == "__main__": sys.exit(main())`
    - Load training points (reading only `train_points.csv`), call `fit_model`, and on success write the Model_Artifact and Metadata_Report under `Results/`, print a success summary, exit zero
    - On missing/unreadable/zero-row training points or validation failure: write neither artifact, print cause to stderr, exit non-zero (catch `FileNotFoundError`, `KeyError`, `ValueError`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1_
  - [x]* 8.2 Write example tests for training CLI failure paths
    - Missing/zero-row training points -> non-zero exit, stderr message, no `Results/` artifact written
    - _Requirements: 3.4_

- [x] 9. Implement `Scripts/predict_site.py` CLI
  - [x] 9.1 Implement the prediction CLI
    - Same CLI pattern; `argparse` with `--profile-id` (required int), `--depths` (optional float list; omitted -> `DEFAULT_DEPTH_GRID`), `--model` (default `MODEL_PATH`), `--sites` (default `CANDIDATE_SITES_PATH`)
    - Load the saved model, call `lookup_candidate_site`, select depths (supplied valid depths override the default grid), call `predict_temperatures` with site lat/lon and start_time as UTC prediction time
    - Emit structured JSON to stdout with `profile_id`, `utc_time`, and ordered `predictions` depth/temperature pairs matching the selected depth order one-to-one; treat depths as requested prediction levels only, never as actual bottom depth
    - Error handling: empty or invalid depths (not finite > 0) -> stderr, no predictions, non-zero exit; unknown profile_id (`KeyError`) -> not-found message, non-zero exit; ambiguous profile_id (`ValueError`) -> ambiguous message, non-zero exit
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 5.2_
  - [x]* 9.2 Write example tests for depth selection and prediction JSON shape
    - **Property 5: Explicit depths override the default grid**
    - **Validates: Requirements 4.2, 4.3, 4.4**
    - Omitted depths -> default grid used; supplied valid depths -> override; JSON output has `profile_id`, `utc_time`, and ordered depth/temperature pairs (Req 4.7)
  - [x]* 9.3 Write example tests for prediction CLI failure paths
    - Unknown profile_id, ambiguous profile_id, and empty/invalid depths each -> non-zero exit, stderr message, no predictions emitted
    - _Requirements: 4.5, 4.6, 4.8_

- [x] 10. Write data-boundary no-open test in `tests/test_model.py`
  - **Property 1: Data boundary — forbidden files never opened**
  - **Validates: Requirements 5.4, 5.5, 5.6**
  - `monkeypatch` spy on `pandas.read_csv` and `builtins.open` recording every opened path; run the training path and the prediction path; assert the recorded set contains neither `heldout_points.csv` nor `profile_summary.csv`
  - _Requirements: 5.4, 5.5, 5.6_

- [x] 11. Write end-to-end smoke test in `tests/test_model.py`
  - Train on real `Data/splits/train_points.csv`, predict one candidate site from `candidate_sites.csv` at a fixed set of depths, assert every returned temperature is finite, and apply the no-open spy across train -> predict to confirm `heldout_points.csv` was not opened
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 12. Update `README.md` and `.kiro/steering/shelfcast-purpose-scope.md` status
  - Set both to "Stage 1 and 2 complete; Stage 3 active" and describe the Stage 3 scope: a first temperature predictor with a hard data boundary; no forecasts, uncertainty, measurement recommendations, maps, spatial visualization, dashboard, UI, deployment, or hosting; groups described only as "candidate profiles", never verified fishing tows or casts
  - _Requirements: 7.1, 7.2, 7.5, 8.1, 8.2_

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation sub-tasks are never optional.
- Each task references specific requirement sub-clauses for traceability.
- All property test tasks are focused, example-based `pytest` tests (no property-based testing framework), each annotated with its design Property number and the requirements it validates.
- Verification is folded into each task; there is no standalone run-the-suite or deployment task.
- Config additions are purely additive; Stage 1 and Stage 2 code, files, and outputs stay unchanged.
- "Candidate profile" wording is preserved anywhere profiles are described.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "7", "12"] },
    { "id": 1, "tasks": ["2.1", "2.3"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.1", "5.1", "6.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "5.2", "6.2"] },
    { "id": 4, "tasks": ["4.2", "4.3", "8.1"] },
    { "id": 5, "tasks": ["8.2", "9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3", "10", "11"] }
  ]
}
```
