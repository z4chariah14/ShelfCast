# ShelfCast — Purpose and Scope

## Purpose

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. The project
is being built in stages.

## Current stage: Stage 1 and 2 complete; Stage 3 active

Stage 1 (the data foundation) and Stage 2 (the chronological replay split) are
complete. Stage 3 (a first temperature predictor) is the active stage. Stage 3
is limited to fitting a single regression model on the Stage 2 training
candidate profiles (`Data/splits/train_points.csv`), a reusable prediction
function, two command-line scripts (training and candidate-site prediction),
the model artifacts written under `Results/`, the supporting documentation, and
focused tests. Across Stage 1, Stage 2, and Stage 3 the project explicitly does
**not** include:

- any forecast, uncertainty or confidence claim, or measurement-location
  recommendation
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

## Stage 3 data boundary (must hold while Stage 3 is active)

Stage 3 model-training and pre-reveal prediction code may read only the
training points (`Data/splits/train_points.csv`) and the candidate-site table
(`Data/splits/candidate_sites.csv`) as observational inputs, plus the model
artifacts it writes under `Results/`. It must never open
`Data/splits/heldout_points.csv` and must never read the hidden
temperature/depth summary columns of `Data/processed/profile_summary.csv`.
Requested prediction depths are requested prediction levels only; they do not
establish the actual bottom depth at a site.

## Study region and grouping rules (Stage 1)

- Study region: latitude 41.5-42.5 N, longitude -70.5 to -69.5.
- Group by identical recorded (latitude, longitude) and consecutive time gaps
  (default 5 minutes).
- Retain groups with at least 10 readings and at least 10 m of depth range.
- No group may span more than one hour; a reading that would exceed one hour
  starts a new group and the earlier portion is retained.
