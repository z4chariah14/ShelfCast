# ShelfCast — Purpose and Scope

## Purpose

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. The project
is being built in stages.

## Current stage: Stage 1 complete; Stage 2 active

Stage 1 (the data foundation) is complete. Stage 2 (the chronological replay
split) is the active stage. Stage 2 is limited to splitting the Stage 1
candidate profiles into a training set and a hidden replay set at a fixed UTC
cutoff, its four local output artifacts (`train_points.csv`,
`heldout_points.csv`, `candidate_sites.csv`, `split_report.json`), the
supporting documentation, and focused tests. Across Stage 1 and Stage 2 the
project explicitly does **not** include:

- any predictive or interpolation model
- any map or spatial visualization
- any dashboard or UI
- any deployment or hosting

Do not add those capabilities while working within the current stage scope, and
do not expand the Stage 1 study region.

## Data integrity rule (must hold across all stages)

The released eMOLT starter ZIP (`Data/raw/emolt.zip`) omits the `tow_id` and
`segment_type` columns that the full eMOLT source provides. Groups produced by
Stage 1 are therefore **provisional candidate profiles** inferred from recorded
position and time proximity.

- Never present these groups as verified fishing tows or casts.
- Use the wording "candidate profile" in outputs and docs, never "tow" or "cast".
- Output artifacts must not contain any tow, cast, or segment-type label.

## Study region and grouping rules (Stage 1)

- Study region: latitude 41.5-42.5 N, longitude -70.5 to -69.5.
- Group by identical recorded (latitude, longitude) and consecutive time gaps
  (default 5 minutes).
- Retain groups with at least 10 readings and at least 10 m of depth range.
- No group may span more than one hour; a reading that would exceed one hour
  starts a new group and the earlier portion is retained.
