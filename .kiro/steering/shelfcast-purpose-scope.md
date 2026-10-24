# ShelfCast — Purpose and Scope

## Purpose

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. The project
is being built in stages.

## Current stage: Stages 1-3 complete; Stage 4 active

Stage 1 (the data foundation), Stage 2 (the chronological replay split), and
Stage 3 (a first temperature predictor) are complete. Stage 4 (a local,
read-only viewer) is the active stage.

Stage 3 remains limited to fitting a single regression model on the Stage 2
training candidate profiles (`Data/splits/train_points.csv`), a reusable
prediction function, two command-line scripts (training and candidate-site
prediction), the model artifacts written under `Results/`, the supporting
documentation, and focused tests.

Stage 4 is limited to a single local Streamlit app (`app.py`, launched with
`streamlit run app.py`) plus a small importable helper module
(`shelfcast/viewer.py`) and focused tests. The app loads the existing saved
model and metadata from `Results/`, shows training and candidate-profile
locations on a map, lets the user select a candidate profile, and charts the
Stage 3 predicted temperatures at the declared standard depths for that site and
its recorded UTC start time. It reuses the existing `predict_temperatures`
function unchanged and is strictly read-only (it never retrains or modifies the
model).

Across all stages the project explicitly does **not** include:

- any forecast, uncertainty or confidence claim, or measurement-location
  recommendation
- any model retraining or next-site recommendation in Stage 4
- any deployment or hosting

Stage 4 does add a map and a local UI (that is its purpose), but it must not add
any of the excluded capabilities above, must not expand the Stage 1 study
region, and must not rewrite Stages 1-3.

## Data integrity rule (must hold across all stages)

The released eMOLT starter ZIP (`Data/raw/emolt.zip`) omits the `tow_id` and
`segment_type` columns that the full eMOLT source provides. Groups produced by
Stage 1 are therefore **provisional candidate profiles** inferred from recorded
position and time proximity.

- Never present these groups as verified fishing tows or casts.
- Use the wording "candidate profile" in outputs and docs, never "tow" or "cast".
- Output artifacts must not contain any tow, cast, or segment-type label.

## Data boundary (must hold while Stage 3 or Stage 4 is active)

Stage 3 and Stage 4 pre-reveal code may read only the training points
(`Data/splits/train_points.csv`) and the candidate-site table
(`Data/splits/candidate_sites.csv`) as observational inputs, plus the model
artifacts written under `Results/`. It must never open
`Data/splits/heldout_points.csv` and must never read the hidden
temperature/depth summary columns of `Data/processed/profile_summary.csv`.
Requested prediction depths are requested prediction levels only; they do not
establish the actual bottom depth at a site.

The Stage 4 viewer additionally must never display or otherwise reveal any
actual hidden temperature or depth value; it shows recorded coordinates/time and
model-predicted temperatures only.

## Study region and grouping rules (Stage 1)

- Study region: latitude 41.5-42.5 N, longitude -70.5 to -69.5.
- Group by identical recorded (latitude, longitude) and consecutive time gaps
  (default 5 minutes).
- Retain groups with at least 10 readings and at least 10 m of depth range.
- No group may span more than one hour; a reading that would exceed one hour
  starts a new group and the earlier portion is retained.
