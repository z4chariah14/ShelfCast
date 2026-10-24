# ShelfCast

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. This
repository currently contains **Stage 1 (data foundation)**, **Stage 2
(chronological replay split)**, **Stage 3 (a first temperature predictor)**,
**Stage 4 (a local, read-only viewer)**, **Stage 5 (a controlled reveal
loop)**, and **Stage 6 (a five-model spread and a suggested next
measurement)**. Stages 1-5 are complete and Stage 6 is the active stage. There
is still no deployment or hosting, no forecast, no calibrated uncertainty or
confidence interval, and no oxygen, weather, or new research model. Stage 5 adds
a temporary, in-memory model update after an explicit reveal, and Stage 6 adds
five in-memory spread models and one suggested candidate profile to test — none
of which ever overwrite the saved model.

## Quickstart (for reviewers)

The raw eMOLT data, the generated splits, and the trained model are **not**
tracked in Git (they are local build artifacts). From a clean clone, run these
steps from the project root to build everything and launch the app:

```bash
# 1. Install dependencies (Python 3.11+ recommended)
python -m pip install -r requirements.txt

# 2. Download the eMOLT starter ZIP into Data/raw/
#    URL: https://hackachusetts2026.vercel.app/kits/emolt.zip
#    Save it exactly as Data/raw/emolt.zip
#    (curl example; any download method works)
curl -L https://hackachusetts2026.vercel.app/kits/emolt.zip -o Data/raw/emolt.zip

# 3. Build the data + model artifacts (Stage 1 -> 2 -> 3)
python Scripts/prepare_data.py     # Data/processed/
python Scripts/split_replay.py     # Data/splits/
python Scripts/train_model.py      # Results/model.joblib + metadata

# 4. Launch the local app (opens in your browser)
streamlit run app.py
```

PowerShell note (Windows): step 2 can use
`Invoke-WebRequest https://hackachusetts2026.vercel.app/kits/emolt.zip -OutFile Data/raw/emolt.zip`.

Once the app is running, select a candidate profile to see the Stage 3
prediction, the five-model spread band, and the suggested next measurement.
Press **Reveal actual measurements** to reveal that one profile's hidden
readings and the updated spread/suggestion, and **Reset replay** to return to
the pre-reveal view.

To run the test suite instead:

```bash
python -m pytest
```

## What Stage 1 does

The Stage 1 pipeline turns the released eMOLT starter archive into three
reviewable artifacts:

- `Data/processed/profile_points.csv` — every retained reading with a `profile_id`
- `Data/processed/profile_summary.csv` — one row per provisional candidate profile
- `Data/processed/stage1_report.json` — input, duplicate, rejected, regional,
  retained, and profile counts plus the grouping rules

It loads the ZIP directly, parses UTC times and numeric values, removes exact
duplicate rows, reports missing/invalid rows, restricts to the study region
(latitude 41.5-42.5 N, longitude -70.5 to -69.5), and groups nearby readings
into **provisional candidate profiles** using the same recorded location and
short consecutive time gaps.

### Provisional candidate profiles (important)

The released starter ZIP omits the `tow_id` and `segment_type` columns that the
full eMOLT source provides. Because Stage 1 cannot see verified tow or cast
boundaries, every group it produces is a *provisional candidate profile*
inferred from recorded position and time proximity. These groups are **not**
verified fishing tows or casts.

## Setup

Install the Python dependencies:

    python -m pip install -r requirements.txt

Download the [released eMOLT starter ZIP](https://hackachusetts2026.vercel.app/kits/emolt.zip) and save it as Data/raw/emolt.zip. The raw ZIP is kept local and is not tracked in Git.

## Run it

From the project root:

```
python Scripts/prepare_data.py
```

Options:

- `--input` path to the raw ZIP (default `Data/raw/emolt.zip`)
- `--output` output directory (default `Data/processed`)
- `--gap-minutes` consecutive-gap threshold in minutes (default 5)

## Stage 2: chronological replay split

Stage 2 splits the Stage 1 **provisional candidate profiles** into a training
set and a hidden replay set at a fixed UTC cutoff (`2024-08-06T00:00:00Z`).
Each candidate profile is classified as a whole using its recorded start and
end times:

- a profile that **ends before** the cutoff is training data,
- a profile that **starts at or after** the cutoff is hidden replay data,
- a profile that **spans** the cutoff (including one whose end time is exactly
  the cutoff) is excluded from both sets and reported.

A profile's readings are never divided across sets. These groups remain
provisional candidate profiles inferred from recorded position and time
proximity — they are never verified fishing tows or casts.

Before writing anything, Stage 2 runs integrity checks and aborts (writing no
files, exiting non-zero) if any fails: the summary and point profile ids must
match, each profile id must appear once with summary times equal to its
earliest/latest readings, the training and held-out id sets must be disjoint,
and the candidate-sites file must carry no hidden measurement columns.

### Run it

From the project root:

```
python Scripts/split_replay.py
```

Options:

- `--processed` path to the Stage 1 outputs (default `Data/processed`)
- `--output` / `--splits` output directory (default `Data/splits`)

### Stage 2 outputs

Written to `Data/splits/` (kept local, not tracked in Git):

- `train_points.csv` — full readings for the training candidate profiles
- `heldout_points.csv` — full readings for the hidden replay candidate profiles
- `candidate_sites.csv` — replay sites, with only `profile_id, latitude,
  longitude, start_time` (no temperature, depth, or other hidden measurements)
- `split_report.json` — per-set counts and UTC time ranges, the list of
  excluded spanning profiles, and the cutoff

## Stage 3: first temperature predictor

Stage 3 fits a first, working temperature predictor on the Stage 2 training
**candidate profiles** and predicts ocean temperature at a given location, UTC
time, and set of requested prediction depths. The model is an
`ExtraTreesRegressor` (scikit-learn) with a fixed random seed, using exactly
four inputs: latitude, longitude, depth in metres, and UTC time expressed as
hours since a fixed reference instant.

Stage 3 holds a strict **data boundary**: training and pre-reveal prediction
code read only `Data/splits/train_points.csv` and
`Data/splits/candidate_sites.csv` (plus the model artifacts it writes under
`Results/`). It never opens `Data/splits/heldout_points.csv` and never reads the
hidden temperature/depth summary columns of
`Data/processed/profile_summary.csv`. Requested depths are requested prediction
levels only; they do not establish the actual bottom depth at a site. Stage 3
adds no forecasts, uncertainty claims, measurement recommendations, maps, UI, or
deployment, and leaves Stage 1 and Stage 2 unchanged. These groups remain
provisional candidate profiles inferred from recorded position and time
proximity -- never verified fishing tows or casts.

### Train the model

From the project root:

```
python Scripts/train_model.py
```

Writes `Results/model.joblib` (the fitted model) and `Results/model_metadata.json`
(feature order, time reference, random seed, training row and candidate-profile
counts, and the candidate-profile integrity note).

Options:

- `--train` path to the training points (default `Data/splits/train_points.csv`)
- `--model` output model path (default `Results/model.joblib`)
- `--metadata` output metadata path (default `Results/model_metadata.json`)

### Predict for a candidate site

```
python Scripts/predict_site.py --profile-id 4
```

Looks up the candidate profile's recorded latitude, longitude, and start time
from `candidate_sites.csv`, predicts temperature at the default depth grid, and
prints a structured JSON object with the `profile_id`, the UTC time, and ordered
depth/temperature pairs.

Options:

- `--profile-id` candidate profile id to predict for (required)
- `--depths` explicit requested prediction levels in metres (finite, > 0);
  omit to use the default depth grid
- `--model` path to the saved model (default `Results/model.joblib`)
- `--sites` path to the candidate-sites table (default
  `Data/splits/candidate_sites.csv`)

## Stage 4: local viewer

Stage 4 adds a single local, read-only **Streamlit app** that makes the
already-trained Stage 3 predictor explorable. It loads the saved model and
metadata from `Results/`, shows the training locations and candidate-profile
locations on a map, lets you select a candidate profile, and charts the Stage 3
predicted temperatures at the declared standard depths for that site and its
recorded UTC start time. It reuses the existing `predict_temperatures` function
unchanged, so the chart matches the Stage 3 prediction CLI exactly.

The app shows units (°C, metres), eMOLT source attribution, a "historical
replay" note, and the provisional-candidate-profile and unknown-bottom-depth
limitations. It is strictly read-only: it never retrains or modifies the model,
and it adds no uncertainty estimate, next-site recommendation, forecast, or
deployment.

Stage 4 holds the same hard **data boundary** as Stage 3: it reads only
`train_points.csv` and `candidate_sites.csv` (plus the `Results/` artifacts),
never opens `heldout_points.csv` or `profile_summary.csv`, and never displays a
hidden temperature or depth value. Map layers use recorded latitude/longitude
only.

### Run it

First make sure a model exists (`python Scripts/train_model.py`), then from the
project root:

```
streamlit run app.py
```

The app uses libraries already in `requirements.txt` (Streamlit, pydeck,
altair). Install them with `python -m pip install -r requirements.txt` if needed.

## Stage 5: controlled reveal loop

Stage 5 extends the Stage 4 viewer with a controlled **reveal loop**. You still
select a provisional candidate profile and see the Stage 3 predicted
temperature curve, but now you can press **Reveal actual measurements** to
reveal that one profile's hidden historical readings, then press **Reset
replay** to return to the pre-reveal view.

On reveal the app:

- overlays the revealed profile's real temperature readings at their **true
  recorded depths** (not snapped to the requested prediction levels),
- fits a **temporary, in-memory model** from the original training rows plus
  only that one revealed profile, and charts the original vs updated predicted
  curves for the selected site,
- picks one **nearby still-hidden candidate site** and shows its original vs
  updated predicted curves, a recolored map marker, and a numeric prediction
  change at the 20 m requested prediction level.

The nearby site is the geographically nearest candidate (by great-circle
distance in **kilometres**) that is both **at least 1 km away** from the
selected site and **starts after** the revealed profile's final recorded
measurement. If none qualifies, the app shows a "no eligible nearby site"
message. The nearby site's own hidden measurements are never read -- its
before/after values come from model predictions only.

Stage 5 keeps the Stage 3/4 **data boundary**. `Data/splits/heldout_points.csv`
is opened only by `shelfcast.reveal.read_revealed_profile`, only after the
reveal click, and only the selected profile's rows are ever returned, used,
stored, or shown. Startup, the map, caching, and site selection never open it,
and nothing reads the hidden columns of `Data/processed/profile_summary.csv`.
The temporary model lives in memory only and **never overwrites**
`Results/model.joblib`; changing the selected profile or pressing Reset replay
discards the revealed data and returns to the saved model. If the heldout file
is missing, the app reports it and tells you to run the Stage 2 split. This
remains a historical replay (the model was trained only on candidate profiles
that ended before the 2024-08-06 00:00 UTC cutoff; the revealed profiles started
on or after it), with no uncertainty band, next-site recommendation, forecast,
or deployment.

### Run it

First make sure a model and the Stage 2 splits exist (`python
Scripts/split_replay.py` then `python Scripts/train_model.py`), then from the
project root:

```
streamlit run app.py
```

The app uses libraries already in `requirements.txt` (Streamlit, pydeck,
altair).

## Stage 6: five-model spread and a suggested next measurement

Stage 6 extends the Stage 5 viewer with two exploratory views, keeping the
Stage 3 prediction and the Stage 5 reveal charts intact. A single new importable
module, `shelfcast/spread.py`, holds all Stage 6 logic.

- **Five-model spread.** It fits exactly five reproducible versions of the
  existing ExtraTrees model by resampling **whole training candidate profiles**
  with replacement — never individual readings — using fixed per-model seeds, so
  the five models and their predictions are reproducible run to run. At the
  selected site the app shades the minimum-to-maximum range of the five models'
  predicted curves. This is **spread across five models — an exploratory
  measure, not a calibrated confidence interval.**
- **Suggested next measurement.** It scores eligible historical candidate
  profiles from `candidate_sites.csv` by how much the five models disagree at
  the 5 m and 10 m requested prediction levels, and suggests the single
  highest-disagreement candidate (ties broken by lowest `profile_id`), with its
  score and a plain-language reason. Before a reveal, a candidate must start
  after the selected site's start time; after a reveal, after the revealed
  profile's final measurement. The selected site and any site within 1 km are
  excluded. The result is **a profile to test, never an optimal site or an
  operational boat route.**

After an explicit reveal, the spread and the suggestion are recomputed from the
training profiles plus **only** the one selected revealed profile (that revealed
profile is included in every updated model). The updated models live in memory
only; a selection change or **Reset replay** discards them and returns the app
to the pre-reveal spread and suggestion.

Stage 6 reuses `fit_model` and `predict_temperatures` unchanged and keeps the
Stage 1-5 **data boundary**: `shelfcast/spread.py` opens no data files of its
own — it receives only in-memory frames (the training rows and, after a reveal,
only the one revealed profile's rows already read by `shelfcast/reveal.py`) plus
the candidate-site coordinate/time columns. It never opens `heldout_points.csv`
or the hidden columns of `profile_summary.csv`, no spread or updated model is
written to disk or over `Results/model.joblib`, the suggestion is computed from
predictions only, and the study region, chronological split,
provisional-candidate-profile wording, historical-replay framing, and
unknown-bottom-depth caveat are all preserved. Stage 6 adds no forecast,
calibrated uncertainty, oxygen, weather, new research model, or deployment.

### Run it

Same launch as Stage 4/5 (a model and the Stage 2 splits must exist):

```
streamlit run app.py
```

## Tests

```
python -m pytest
```

Runtime code depends on pandas, numpy, scikit-learn, and joblib (plus the Python
standard library). The Stage 4-6 viewer additionally depends on Streamlit,
pydeck, and altair. Running the tests additionally requires pytest.

## Dataset attribution

Ocean temperature observations from the **eMOLT** (Environmental Monitors on Lobster
Traps and Large Trawlers) program, retrieved via the ondeckdata ERDDAP server
(`erddap.ondeckdata.com`), covering 1-7 Aug 2024. Source metadata and license: [eMOLT ERDDAP info](https://erddap.ondeckdata.com/erddap/info/emolt_data/index.htmlTable) (free use and redistribution; not intended for legal use).


