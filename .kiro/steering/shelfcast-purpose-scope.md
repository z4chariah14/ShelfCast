# ShelfCast — Purpose and Scope

## Purpose

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. The project
is being built in stages.

## Current stage: Stages 1-5 complete, Stage 6 active

Stage 1 (the data foundation), Stage 2 (the chronological replay split),
Stage 3 (a first temperature predictor), Stage 4 (a local, read-only
viewer), and Stage 5 (a controlled reveal loop) are complete. Stage 6 (a
five-model spread and a suggested next measurement) is the active stage.

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

Stage 6 is limited to extending that same local Streamlit app plus a single new
importable spread module (`shelfcast/spread.py`) and focused tests. It fits
exactly five reproducible versions of the existing ExtraTrees model by
resampling **whole training candidate profiles** (never individual readings),
using fixed per-model seeds, and at a selected site shows the minimum-to-maximum
range of their predicted temperature curves, labeled "spread across five
models — an exploratory measure, not a calibrated confidence interval." It keeps
the existing Stage 3 prediction and the Stage 5 reveal charts. It also suggests
ONE eligible historical candidate location from `candidate_sites.csv` using the
five models' disagreement at the requested depths of 5 m and 10 m: before a
reveal the candidate must start after the selected site's start time; after a
reveal it must start after the revealed profile's final measurement; the
selected site and any site within 1 km are excluded; score ties break by lowest
profile id; the score and a plain-language reason are shown, and it is called a
suggestion to test, never an optimal site or an operational boat route. After a
reveal the spread and the suggestion are recomputed from the training profiles
plus only the one selected revealed profile (that revealed profile is included
in every updated model; the updated models are held in memory). A selection
change and "Reset replay" clear all updated state. Stage 6 reuses `fit_model`
and `predict_temperatures` unchanged.

Across all stages the project explicitly does **not** include:

- any forecast, calibrated uncertainty or confidence interval, or
  measurement-location recommendation presented as optimal
- any next-site recommendation presented as an optimal site or an operational
  boat route
- any oxygen value, weather value, new research model, deployment, or hosting

Stage 5 adds a reveal of one hidden historical profile, a temporary model
update, and the nearby-site map/delta; Stage 6 adds the five-model spread and
the one suggested candidate profile to test (that is their purpose). Neither
stage may add any of the excluded capabilities above, expand the Stage 1 study
region, rewrite earlier stages, or save any temporary/spread/updated model over
`Results/model.joblib`; both present everything as a historical replay rather
than a live forecast. The five-model spread is an exploratory measure, not a
calibrated confidence interval, and the suggestion is a profile to test, not an
optimal site or a boat route.

## Historical replay framing (Stage 5 and Stage 6)

The chronological replay split (Stage 2) means TRAINING candidate profiles ended
(`end_time`) strictly before the cutoff of 2024-08-06T00:00:00Z UTC, while HIDDEN
(heldout) candidate profiles started (`start_time`) on or after that cutoff. The
selected hidden profile therefore started on or after the cutoff, while the
original saved model was trained only on profiles that ended before it. Describe
Stage 5 and Stage 6 this way; do not describe them as showing "records before the
cutoff".

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

## Data boundary (must hold while Stage 3, Stage 4, Stage 5, or Stage 6 is active)

Stage 3, Stage 4, and all Stage 5 and Stage 6 PRE-REVEAL code may read only the
training points (`Data/splits/train_points.csv`) and the candidate-site table
(`Data/splits/candidate_sites.csv`) as observational inputs, plus the model
artifacts written under `Results/`. This pre-reveal boundary covers every
startup, map, cache, site-selection, pre-reveal prediction, model-loading,
spread-fit, scoring, and suggestion path. These paths must never open
`Data/splits/heldout_points.csv` and must never read the hidden temperature/depth
summary columns of `Data/processed/profile_summary.csv`. Requested prediction
depths are requested prediction levels only; they do not establish the actual
bottom depth at a site.

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

Stage 6 does not widen this exception. `shelfcast/spread.py` opens no data files
of its own; it receives only in-memory frames — the training rows and, after a
reveal, ONLY the one selected revealed profile's rows already read by
`shelfcast/reveal.py` — plus the candidate-site coordinate/time columns. No other
hidden profile value may enter any spread fit, disagreement score, chart, or
cache. The five pre-reveal spread models and the five updated post-reveal models
are held in memory only and must never be written over `Results/model.joblib` or
any other file. The updated spread models and the suggestion derived from them
are reveal-scoped: a selection change or "Reset replay" must discard them and
return the app to the pre-reveal spread and pre-reveal suggestion. The suggestion
is computed from model predictions only and never reads or displays any hidden
`temperature_c`/`depth_m` value for a scored or suggested candidate.

The nearby still-hidden candidate site's actual temperatures and depths are
never read or displayed; its map update and numeric delta are computed from model
predictions only. The Stage 4 viewer (and every Stage 5 and Stage 6 pre-reveal
path) must never display or otherwise reveal any actual hidden temperature or
depth value; only after the explicit Stage 5 reveal may the one selected
profile's actual measurements be shown, at their true recorded depths.

## Study region and grouping rules (Stage 1)

- Study region: latitude 41.5-42.5 N, longitude -70.5 to -69.5.
- Group by identical recorded (latitude, longitude) and consecutive time gaps
  (default 5 minutes).
- Retain groups with at least 10 readings and at least 10 m of depth range.
- No group may span more than one hour; a reading that would exceed one hour
  starts a new group and the earlier portion is retained.