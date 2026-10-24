# Implementation Plan: ShelfCast Stage 4 Local Viewer

## Overview

Build the Stage 4 viewer thinnest-testable-piece first: the importable
`shelfcast/viewer.py` helpers (loaders with `usecols` whitelists and the
site-prediction table that reuses the Stage 3 prediction path), then the
`app.py` Streamlit UI and ocean theme, then focused boundary/parity tests, then
the status-doc updates and dependency pins. All code references only
`train_points.csv`, `candidate_sites.csv`, and the `Results/` artifacts;
`heldout_points.csv` and `profile_summary.csv` are never opened. Groups are
described only as "candidate profiles". Stage 1-3 code and outputs stay
unchanged.

## Tasks

- [x] 1. Implement `shelfcast/viewer.py` app-only helpers
  - `load_metadata` / `load_fitted_model` reading `Results/` (raise
    `FileNotFoundError` if missing); `load_fitted_model` delegates to
    `shelfcast.model.load_model`
  - `load_training_locations` reads ONLY `[latitude, longitude]` via `usecols`;
    `load_candidate_sites` reads ONLY the four allowed columns
    `[profile_id, latitude, longitude, start_time]`
  - `predict_site_table(model, site, depths)` reuses
    `shelfcast.model.predict_temperatures` and returns a `depth_m`/`temperature_c`
    DataFrame, one row per depth, in order; opens no file
  - _Requirements: 1.1, 1.2, 3.2, 4.1, 4.2, 6.2, 6.3, 7.2_

- [x] 2. Implement `app.py` Streamlit UI at the project root
  - Page config + ocean theme; title using "candidate profile" wording
  - Load artifacts via `viewer.py`; if model/metadata missing, show guidance to
    run `python Scripts/train_model.py` and `st.stop()` (no prediction)
  - pydeck map with two distinguishable layers (training vs candidate sites),
    recorded lat/lon only, legend labeling candidate markers as candidate profiles
  - `st.selectbox` of candidate `profile_id`; on select, `lookup_candidate_site`
    and show recorded lat/lon + UTC start time
  - altair chart of predicted temperature (°C) vs depth (m, inverted), units in
    axis titles, plus a companion table; predictions presented as model output
    only
  - Context panel: eMOLT attribution, "historical replay", provisional
    candidate-profile limitation, unknown-bottom-depth limitation
  - _Requirements: 1.1, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1, 3.3, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 7.1, 7.4_

- [x] 3. Add the ocean theme file `.streamlit/config.toml`
  - Restrained ocean palette (deep-navy primary, light background); declarative,
    no heavy CSS
  - _Requirements: 7.5_

- [x] 4. Add app dependencies to `requirements.txt`
  - Pin `streamlit`, `pydeck`, `altair` at the installed versions; do not remove
    existing Stage 1-3 dependencies
  - _Requirements: 7.5_

- [x]* 5. Write focused tests in `tests/test_viewer.py`
  - Data-boundary spy: wrap `pandas.read_csv` + `builtins.open`, run all loaders
    and one `predict_site_table`, assert neither `heldout_points.csv` nor
    `profile_summary.csv` opened (Property 1)
  - CLI parity: `predict_site_table` for a real profile equals
    `predict_temperatures` called directly with the Stage 3 CLI's inputs
    (Property 2)
  - Depth contract: one row per `DEFAULT_DEPTH_GRID` depth, in order, all finite
    (Property 3)
  - usecols whitelist: `load_training_locations` reads only lat/lon;
    `load_candidate_sites` reads only the four allowed columns
  - _Requirements: 4.1, 4.2, 6.1, 6.2, 6.3, 6.4, 7.2_

- [x] 6. Update `README.md` and `.kiro/steering/shelfcast-purpose-scope.md`
  - Set both to "Stages 1-3 complete; Stage 4 active", preserving historical
    stage descriptions
  - README: describe the app, how to launch (`streamlit run app.py`), and the
    data boundary; steering: add a Stage 4 scope + data-boundary section
  - _Requirements: 8.1, 8.2_

- [x] 7. Verify
  - Confirm the app launches with `streamlit run app.py` (headless smoke)
  - Confirm a selected site's chart values equal the Stage 3 CLI output for the
    same profile/depths
  - Confirm the full test suite still passes
  - _Requirements: 4.2, 6.4, 7.2_

## Notes

- Task 5 (tests) is marked optional with `*`; core implementation tasks 1-4, 6,
  and verification 7 are not optional.
- `app.py` stays thin and declarative; all testable logic lives in `viewer.py`.
- The prediction path is reused from Stage 3 verbatim to guarantee CLI parity.
- Config/data/model artifacts from Stage 1-3 are not modified.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "3", "4"] },
    { "id": 1, "tasks": ["2", "5"] },
    { "id": 2, "tasks": ["6"] },
    { "id": 3, "tasks": ["7"] }
  ]
}
```
