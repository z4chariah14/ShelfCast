# ShelfCast — Purpose and Scope

## Purpose

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. The project
is being built in stages.

## Current stage: Stages 1-5 complete

Stage 1 (the data foundation), Stage 2 (the chronological replay split),
Stage 3 (a first temperature predictor), Stage 4 (a local, read-only
viewer), and Stage 5 (a controlled reveal loop) are complete.

Stage 3 remains limited to fitting a single regression model on the Stage 2
training candidate profiles (`Data/splits/train_points.csv`), a reusable
prediction function, two command-line scripts (training and candidate-site
prediction), the model artifacts written under `Results/`, the supporting
documentation, and focused tests.

Stage 4 remains limited to a single local Streamlit app (`app.py`, launched
with `streamlit run app.py`) plus a small importable helper module
(`shelfcast/viewer.py`) and focused tests. The app loads the existing saved
model and metadata from `Results/`, shows training and candidate-profile
locations on a map, lets the user select a candidate profile, and charts the
Stage 3 predicted temperatures at the declared standard depths for that site and
its recorded UTC start time. It reuses the existing `predict_temperatures`
function unchanged and is strictly read-only (it never retrains or modifies the
model).

Stage 5 is limited to extending that same local Streamlit app plus a single new
importable reveal module (`shelfcast/reveal.py`) and focused tests. It adds a
controlled, explicit reveal of ONE selected hidden historical candidate profile
and a visible, temporary model update. Before any reveal the app shows the
existing Stage 4 prediction. After the user presses "Reveal actual
measurements", a dedicated reveal function reads only the selected profile's
rows from `Data/splits/heldout_points.csv`, overlays those real temperature
readings at their actual recorded depths, refits a temporary in-memory model
from the original training rows plus only that one selected profile, and shows
the original and updated predicted curves for the selected site. For one nearby
still-hidden candidate site it shows the before/after predicted curves, a
minimal before/after map-marker update at one requested prediction level
(20 m), and the numeric prediction change (updated minus original) at that
level — all predictions only, never reading that site's hidden measurements. A
"Reset replay" control clears the revealed data and the temporary model and
returns the app to the original saved model and the pre-reveal display. Stage 5
reuses `fit_model` and `predict_temperatures` unchanged.

Across all stages the project explicitly does **not** include:

- any forecast, uncertainty or confidence claim, or measurement-location
  recommendation
- any next-site recommendation
- any deployment or hosting

Stage 5 does add a reveal of one hidden historical profile, a temporary model
update, and the nearby-site map/delta (that is its purpose), but it must not add
any of the excluded capabilities above, must not expand the Stage 1 study
region, must not rewrite Stages 1-4, must never save the temporary model over
`Results/model.joblib`, and must present everything as a historical replay
rather than a live forecast.

## Historical replay framing (Stage 5)

The chronological replay split (Stage 2) means TRAINING candidate profiles ended
(`end_time`) strictly before the cutoff of 2024-08-06T00:00:00Z UTC, while HIDDEN
(heldout) candidate profiles started (`start_time`) on or after that cutoff. The
selected hidden profile therefore started on or after the cutoff, while the
original saved model was trained only on profiles that ended before it. Describe
Stage 5 this way; do not describe it as showing "records before the cutoff".

## Data integrity rule (must hold across all stages)

The released eMOLT starter ZIP (`Data/raw/emolt.zip`) omits the `tow_id` and
`segment_type` columns that the full eMOLT source provides. Groups produced by
Stage 1 are therefore **provisional candidate profiles** inferred from recorded
position and time proximity.

- Never present a candidate profile AS a verified fishing tow or cast.
- The words "tow" and "cast" may appear only inside a truthful limitation note
  that explains the starter data omits `tow_id`/`segment_type` so the groups are
  provisional candidate profiles, not verified tows or casts. Prefer the wording
  "candidate profile" everywhere else.
- Output artifacts must not contain any tow, cast, or segment-type label.

## Data boundary (must hold while Stage 3, Stage 4, or Stage 5 is active)

Stage 3, Stage 4, and all Stage 5 PRE-REVEAL code may read only the training
points (`Data/splits/train_points.csv`) and the candidate-site table
(`Data/splits/candidate_sites.csv`) as observational inputs, plus the model
artifacts written under `Results/`. This pre-reveal boundary covers every
startup, map, cache, site-selection, pre-reveal prediction, and model-loading
path. These paths must never open `Data/splits/heldout_points.csv` and must
never read the hidden temperature/depth summary columns of
`Data/processed/profile_summary.csv`. Requested prediction depths are requested
prediction levels only; they do not establish the actual bottom depth at a site.

Stage 5 adds a single, narrow POST-REVEAL exception: one dedicated reveal
function (`shelfcast/reveal.py`), called only after the explicit "Reveal actual
measurements" click, may open `Data/splits/heldout_points.csv`. Only the
selected profile's rows may be returned, used, stored in memory/session state,
used for fitting, or shown — no other profile's rows may be returned, retained,
used, or displayed. It must validate that the selected `profile_id` exists and
return a descriptive error naming the id when it does not. No other code path may
open the heldout file, and no code may read the hidden summary columns of
`profile_summary.csv`. The temporary model fit from the revealed profile is held
in memory only and must never overwrite `Results/model.joblib`. When the selected
profile changes, when "Reset replay" is pressed, or when the replay resets,
revealed values and the temporary model must be discarded and the app must
return to the original saved model and the pre-reveal display; Streamlit reruns
and caching must never accidentally reveal another profile or carry a stale
reveal across selections.

The nearby still-hidden candidate site's actual temperatures and depths are
never read or displayed; its map update and numeric delta are computed from model
predictions only. The Stage 4 viewer (and every Stage 5 pre-reveal path) must
never display or otherwise reveal any actual hidden temperature or depth value;
only after the explicit Stage 5 reveal may the one selected profile's actual
measurements be shown, at their true recorded depths.

## Study region and grouping rules (Stage 1)

- Study region: latitude 41.5-42.5 N, longitude -70.5 to -69.5.
- Group by identical recorded (latitude, longitude) and consecutive time gaps
  (default 5 minutes).
- Retain groups with at least 10 readings and at least 10 m of depth range.
- No group may span more than one hour; a reading that would exceed one hour
  starts a new group and the earlier portion is retained.