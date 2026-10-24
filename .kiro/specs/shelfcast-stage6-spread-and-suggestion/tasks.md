# Implementation Plan: ShelfCast Stage 6 — Spread and Suggestion

## Overview

Incremental, test-driven steps that add the five-model spread and the single
suggested next measurement on top of the Stage 5 reveal loop. Stages 1-5 are
reused unchanged (`fit_model`, `predict_temperatures`, `reveal.haversine_km`,
`reveal.revealed_final_time`, `reveal.MIN_NEARBY_KM`, `reveal.reset_reveal_state`).
The only new module is `shelfcast/spread.py`; `reveal.py` stays the only path to
`heldout_points.csv`. The essential tests in task 6 are REQUIRED for the MVP.

## Tasks

- [x] 1. Add Stage 6 config constants
  - Append `SPREAD_N_MODELS = 5`, `SPREAD_SEEDS = [101, 202, 303, 404, 505]`,
    and `SPREAD_SCORE_DEPTHS = [5.0, 10.0]` to `shelfcast/config.py` (additive;
    no other change).
  - _Requirements: 1.1, 1.3, 3.1_

- [x] 2. Create the Spread_Engine module `shelfcast/spread.py`
  - [x] 2.1 `resample_profiles(train_df, seed)`
    - Seeded numpy Generator; sample whole profile ids WITH replacement and
      include every reading of each sampled profile; never sample individual
      readings; require >= 2 distinct profile ids (else `ValueError`).
    - _Requirements: 1.1, 1.2, 1.5_
  - [x] 2.2 `fit_spread_models(train_df, revealed_df=None, seeds=SPREAD_SEEDS)`
    - For each seed, resample profiles (plus the one revealed profile's rows
      forced into every resample when `revealed_df` is given) and call
      `model.fit_model` unchanged on the combined source-column frame. Return the
      five estimators in memory; never write to disk.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 6.1, 6.3, 6.4_
  - [x] 2.3 `spread_table(models, site, depths=DEFAULT_DEPTH_GRID)`
    - Per-depth min/max/mean predicted temperature across the models via
      `predict_temperatures`; return `[depth_m, temp_min, temp_max, temp_mean]`.
      Predictions only.
    - _Requirements: 2.1, 2.5_
  - [x] 2.4 `disagreement_score(models, lat, lon, start_time, depths=SPREAD_SCORE_DEPTHS)`
    - Non-negative sum over 5 m and 10 m of (max - min) predicted temperature
      across the models. Predictions only; reproducible.
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 2.5 `eligible_candidates(...)` and `suggest_candidate(...)`
    - Exclude selected id and candidates < 1 km away (`reveal.haversine_km`);
      keep only `start_time` strictly after `after_time`; choose highest score,
      ties to lowest `profile_id`; return `None` when none eligible. Reads only
      candidate-site columns; never heldout.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.4, 5.5_

- [x] 3. Extend the reveal reset guard for Stage 6 state
  - Add `"spread_models_updated"` to `reveal.REVEAL_STATE_KEYS` so the existing
    `reset_reveal_state` clears the updated spread models together with the
    Stage 5 reveal keys on a selection change or Reset replay.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 4. Checkpoint — ensure all tests pass
  - Run the suite; confirm Stages 1-5 still pass. Ask the user if questions arise.

- [x] 5. Wire the spread and suggestion into `app.py`
  - Add `from shelfcast import spread` and the Stage 6 config imports; add a
    cached full-source-column training loader and a `@st.cache_resource`
    pre-reveal five-model builder.
  - Pre-reveal: draw the min-to-max spread band (Altair area) under the existing
    Stage 3 line, captioned "spread across five models — an exploratory measure,
    not a calibrated confidence interval"; keep the Stage 5 reveal charts intact.
  - Post-reveal: fit updated spread models from `train_df + revealed_df`, store
    in `st.session_state["spread_models_updated"]` keyed to the revealed id, and
    redraw the spread band and suggestion from them.
  - Suggestion panel: show the suggested `profile_id`, its score, and a
    plain-language reason, labeled a profile to test (never optimal site/route);
    show the "no eligible candidate" message when `suggest_candidate` is `None`.
  - Error handling: `< 2 profile ids` → show a message and skip the
    spread/suggestion, leaving Stage 3 + Stage 5 intact.
  - Preserve all Stage 5 framing (historical replay, requested-prediction-level
    labels, eMOLT attribution, provisional-candidate-profile wording, study
    region). Never write a Stage 6 model to disk.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.2, 5.3, 5.4, 6.2, 7.1, 7.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 6. Required essential tests — `tests/test_spread.py`
  - Follow `test_reveal.py` conventions (`open_spy`, `_require_model()`).
  - [x] 6.1 Profile-level resampling test (Property 1) — sampled profiles keep
    all their rows; partial/unsampled profiles never appear. _Req 1.1, 1.2_
  - [x] 6.2 Reproducibility test (Property 2) — two fits give identical
    `spread_table`/`disagreement_score`; single-profile frame raises
    `ValueError`. _Req 1.3, 1.5, 3.4_
  - [x] 6.3 Eligibility + tie-break test (Property 3) — >= 1 km rule,
    strictly-after-`after_time` rule, selected-site exclusion, highest-score
    choice, tie to lowest `profile_id`, `None` case. _Req 4.1, 4.2, 4.3, 5.1, 5.4_
  - [x] 6.4 Reveal/reset isolation test (Property 6) — extended
    `reset_reveal_state` clears `spread_models_updated`; updated fit includes
    exactly the training rows plus the one revealed profile. _Req 6.1, 6.4, 7.1, 7.2_
  - [x] 6.5 Hidden-data boundary test (Property 4/5) — with `open_spy`, pre-reveal
    spread + suggestion never open `heldout_points.csv`/`profile_summary.csv`;
    `fit_spread_models` writes nothing and leaves `Results/model.joblib`
    unchanged. _Req 1.4, 1.6, 3.3, 5.5, 8.1, 8.2, 8.3_

- [x] 7. Final checkpoint — full suite + app smoke check
  - Run the full pytest suite and a Streamlit import/smoke check; confirm the
    data boundary holds and nothing writes `Results/model.joblib`. Update README
    and steering (Stage 5 complete, Stage 6 active). Ask the user if questions
    arise.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

## Notes

- Each task references specific requirement clauses for traceability.
- Stages 1-5 (`fit_model`, `predict_temperatures`, `reveal.*`) and the saved
  `Results/` artifacts are reused unchanged and never rewritten.
- The spread is an exploratory measure, not a calibrated confidence interval; the
  suggestion is a profile to test, never an optimal site or an operational boat
  route.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "3"] },
    { "id": 2, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5"] },
    { "id": 3, "tasks": ["5"] },
    { "id": 4, "tasks": ["7"] }
  ]
}
```

