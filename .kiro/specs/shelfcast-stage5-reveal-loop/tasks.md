# Implementation Plan: ShelfCast Stage 5 — Reveal Loop

## Overview

Incremental, test-driven steps that add the reveal loop on top of the Stage 4
viewer. Stages 1-3 are reused unchanged (`fit_model`, `predict_temperatures`,
`lookup_candidate_site`); the only new module is `shelfcast/reveal.py`, the only
code path permitted to open `heldout_points.csv`. Until the MVP runs, the
essential boundary/behavior tests are REQUIRED; broader Hypothesis property
tests are OPTIONAL (`*`) and follow once the MVP works. Each step builds on the
previous one and ends wired into `app.py`.

## Tasks

- [x] 1. Add Stage 5 config constant
  - Append `HELDOUT_POINTS_PATH = "Data/splits/heldout_points.csv"` to
    `shelfcast/config.py` with a comment noting it is opened only by
    `shelfcast.reveal.read_revealed_profile` (additive; no other change).
  - _Requirements: 3.1, 3.5_

- [x] 2. Create the reveal module
  - [x] 2.1 Implement `read_revealed_profile(profile_id, path=HELDOUT_POINTS_PATH)`
    - New file `shelfcast/reveal.py`; read `heldout_points.csv`, filter to the
      given `profile_id`, return columns `time, latitude, longitude, depth_m,
      temperature_c, profile_id`; raise `FileNotFoundError` when the file is
      absent (Req 3.8) and `KeyError` naming the id when the id is absent (Req
      3.4).
    - This is the only function permitted to open `heldout_points.csv`.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8_

  - [x] 2.2 Implement `load_training_rows(path=TRAIN_POINTS_PATH)` and `fit_temporary_model(train_df, revealed_df)`
    - `load_training_rows` reads only `train_points.csv` (source columns).
    - `fit_temporary_model` concatenates training rows with the one profile's
      revealed rows (columns `time, latitude, longitude, depth_m,
      temperature_c`), calls `model.fit_model` unchanged, returns the in-memory
      estimator, and never writes to disk.
    - _Requirements: 5.1, 5.3_

  - [x] 2.3 Implement `nearest_candidate_site(selected_id, sites_df, after_time)` with `haversine_km` and `revealed_final_time` helpers
    - `haversine_km` computes great-circle distance in kilometres;
      `revealed_final_time` returns the maximum `time` among the revealed rows.
    - `nearest_candidate_site` excludes the selected id and returns the nearest
      eligible candidate: one that is at least 1 km from the selected site (by
      kilometre distance) AND whose recorded `start_time` is strictly after
      `after_time` (the revealed profile's final recorded measurement). Choose
      the nearest eligible by kilometre distance, break ties to lowest
      `profile_id`, and return `None` when no candidate is eligible. Reads only
      `candidate_sites` columns; never reads heldout.
    - _Requirements: 6.1, 6.6_

  - [x] 2.4 Implement `nearby_site_delta(original_model, temp_model, site, depth=20.0)`
    - Return `{"original": float, "updated": float, "delta": float}` where
      `original`/`updated` are each model's `predict_temperatures` output at the
      requested level (default 20 m) for the site's recorded coordinates and UTC
      start time, and `delta == updated - original`. Predictions only; never read
      the nearby site's `temperature_c`/`depth_m` from `heldout_points.csv`. Pure
      and Streamlit-free so the map recolor and numeric delta are unit-testable.
    - _Requirements: 6.4, 6.5_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Reveal-state reset guard
  - [x] 4.1 Add a pure `reset_reveal_state(session_like, selected_profile_id)` helper
    - Small, Streamlit-free helper (in `shelfcast/reveal.py`) that clears
      `revealed_profile_id`, `revealed_df`, `temp_model` whenever the stored id
      does not match the selected id, returning to the original model. This is
      the single clear path shared by the top-of-rerun guard and the "Reset
      replay" button.
    - _Requirements: 7.1, 7.3, 7.4, 7.5_

- [x] 5. Add the reveal trigger, reset, and handler to `app.py`
  - Add `from shelfcast import reveal` and `from shelfcast.config import CUTOFF,
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX`.
  - Run `reset_reveal_state` at the top of each rerun keyed on the selected
    `profile_id`; add a `st.button("Reveal actual measurements")` in unpressed
    state; in the button branch call `reveal.read_revealed_profile`,
    `load_training_rows`, `fit_temporary_model`, `nearest_candidate_site` and
    store results in session state only for the selected id.
  - Add a `st.button("Reset replay")` control whose press clears the three reveal
    session-state keys via the **same** `reset_reveal_state` path as the
    top-of-rerun guard and returns to the original saved model and pre-reveal
    display.
  - Error handling: missing heldout file (`FileNotFoundError`, show a descriptive
    message directing the user to run `Scripts/split_replay.py`), missing id
    (`KeyError`), zero revealed rows, temporary fit failure (`ValueError`), and
    no eligible nearby site — each shows a message and preserves pre-reveal
    predictions without writing the original model.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.8, 4.4, 5.4, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 6. Add the layered selected-site reveal chart to `app.py`
  - `_render_reveal_charts(...)`: layered Altair chart for the selected site with
    the original predicted curve, the temporary predicted curve (distinct
    color), and actual measured points at their true recorded `depth_m` (distinct
    mark, never rounded/re-binned/snapped to standard depths).
  - Nearby still-hidden site chart: original vs temporary predicted curves
    (predictions only, no heldout values) at the standard requested depths.
  - _Requirements: 4.1, 4.2, 4.3, 5.2, 6.2_

- [x] 7. Add the nearby still-hidden site map + metric update to `app.py`
  - Recolor the nearby site's map marker and set a tooltip/label reflecting the
    original-model then temporary-model predicted temperature at 20 m (visible
    color/label change), driven by `reveal.nearby_site_delta`.
  - Show the numeric prediction change at 20 m with `st.metric` (delta =
    temporary minus original). Predictions only; never read the nearby site's
    heldout values. When no eligible nearby site exists, show the "no eligible
    nearby site" message and skip the marker update and metric.
  - _Requirements: 6.3, 6.4, 6.5, 6.6_

- [x] 8. Carry forward Stage 4 framing in `app.py`
  - Historical-replay caption stating training candidate profiles ended
    (`end_time`) strictly before the 2024-08-06T00:00:00Z UTC cutoff while the
    selected hidden profile started (`start_time`) on or after it; label the
    5/10/20/30/50 m grid as requested prediction levels (not bottom depth);
    eMOLT attribution on all Stage 5 output; "candidate profile" wording, with
    "tow"/"cast" appearing only inside the truthful limitation note; restrict
    displayed sites to the study region; add no uncertainty bands, confidence
    claims, next-site recommendations, or forecasts.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 9. Required essential tests (must pass for the MVP)
  - New file `tests/test_reveal.py`, following `test_viewer.py` conventions (the
    `open_spy` fixture recording every `pd.read_csv`/`open` path, and
    `_require_model()` to skip when `Results/model.joblib` is absent). May be
    written as example-based tests first.
  - [x] 9.1 Reveal-gate test
    - With `open_spy`, exercise `viewer.py`/pre-reveal paths (startup, map,
      selection, reset) and assert `heldout_points.csv` and `profile_summary.csv`
      are never opened; then assert the heldout file IS opened only after a
      reveal press, and that `reveal.read_revealed_profile` is the only opener.
    - **Property 6: Pre-reveal and reset states never materialize heldout data**
    - **Validates: Requirements 2.3, 3.3, 3.5, 3.6, 3.7**

  - [x] 9.2 Profile-filter test
    - `read_revealed_profile` returns only rows whose `profile_id` equals the
      selected id, and no other id's rows.
    - **Property 1: Filtered reveal returns only the requested profile**
    - **Validates: Requirements 3.1, 3.2**

  - [x] 9.3 Model-preservation test
    - Spy on `joblib.dump`/`open`; assert `fit_temporary_model` writes nothing
      and the bytes of `Results/model.joblib` are unchanged.
    - **Property 4: Temporary fit writes nothing and preserves the saved model**
    - **Validates: Requirements 5.1, 5.3, 5.4**

  - [x] 9.4 Depth-preservation test
    - Overlay depths equal the revealed `depth_m` values exactly — never rounded,
      re-binned, or snapped to the standard requested depths.
    - **Property 5: Actual points keep their true depths**
    - **Validates: Requirements 4.1, 4.3**

  - [x] 9.5 Reset test
    - A selection change or "Reset replay" press clears `revealed_profile_id`,
      `revealed_df`, and `temp_model` and returns to the original saved model,
      verified via the pure `reset_reveal_state` guard without launching `app.py`.
    - **Property 8: Selection change or reset discards revealed state**
    - **Validates: Requirements 7.1, 7.3, 7.5**

  - [x] 9.6 Nearby-eligibility and missing-file tests
    - Assert `nearest_candidate_site` returns only candidates ≥ 1 km away (via
      `haversine_km`) whose `start_time` is strictly after the revealed profile's
      final measurement (`revealed_final_time`), breaks ties to lowest
      `profile_id`, and returns `None` when none are eligible; and assert
      `read_revealed_profile` raises `FileNotFoundError` when
      `heldout_points.csv` is absent.
    - _Requirements: 6.1, 6.6, 3.8_

- [x] 10. Checkpoint — Ensure the required essential tests pass
  - Ensure the required essential tests pass, ask the user if questions arise.

- [ ] 11. Broader property tests (optional hardening after MVP runs)
  - [ ]* 11.1 Missing-id generative property test
    - **Property 2: Missing id raises a naming error and reveals nothing**
    - Generative check that absent ids raise `KeyError` naming the id.
    - **Validates: Requirements 3.4**

  - [ ]* 11.2 Nearest-site selection/tie-break property test
    - **Property 3: Nearest site is never the selected site**
    - Synthesized site tables exercising the ≥ 1 km and after-final-measurement
      eligibility, ties exhaustively, and the `None` case.
    - **Validates: Requirements 6.1, 6.6**

  - [ ]* 11.3 Nearby-site delta property test
    - **Property 7: Nearby-site delta is the prediction difference at 20 m**
    - Generated model pairs confirm `delta == updated - original` at 20 m with no
      heldout read for the nearby site.
    - **Validates: Requirements 6.4, 6.5**

  - [ ]* 11.4 Generative expansion of filtering and boundary checks
    - Extend the required profile-filter and reveal-gate cases with Hypothesis
      generation beyond the fixed examples.
    - **Property 1 / Property 6 (generative)**
    - **Validates: Requirements 3.1, 3.2, 3.6, 3.7**

- [x] 12. Final checkpoint — Ensure all tests pass
  - Run the full pytest suite and a Streamlit import/smoke check; confirm the
    data boundary holds. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. The
  essential tests in task 9 are REQUIRED (not marked `*`) and must pass for the
  MVP; the broader property tests in task 11 are optional hardening.
- Each task references specific requirement clauses for traceability.
- Property tests use Hypothesis (≥100 iterations), tagged
  `# Feature: shelfcast-stage5-reveal-loop, Property N: <text>`, and live in
  `tests/test_reveal.py` following `test_viewer.py` conventions.
- Stages 1-3 (`fit_model`, `predict_temperatures`, `lookup_candidate_site`) and
  the saved `Results/` artifacts are reused unchanged and never rewritten.
- `app.py` writers (tasks 5, 6, 7, 8) all edit the same file and are kept in
  separate waves to avoid write conflicts.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2.1", "2.3"] },
    { "id": 1, "tasks": ["2.2", "2.4", "4.1"] },
    { "id": 2, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5", "9.6"] },
    { "id": 3, "tasks": ["5"] },
    { "id": 4, "tasks": ["6"] },
    { "id": 5, "tasks": ["7"] },
    { "id": 6, "tasks": ["8"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3", "11.4"] }
  ]
}
```
