# ShelfCast

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. This
repository currently contains **Stage 1 (data foundation)**, **Stage 2
(chronological replay split)**, **Stage 3 (a first temperature predictor)**, and
**Stage 4 (a local, read-only viewer)**. Stages 1-3 are complete; Stage 4 is
active. There is still no deployment or hosting, no retraining, and no
uncertainty, forecast, or measurement-location recommendation.

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

## Tests

```
python -m pytest
```

Runtime code depends on pandas, scikit-learn, and joblib (plus the Python
standard library). The Stage 4 viewer additionally depends on Streamlit, pydeck,
and altair. Running the tests additionally requires pytest.

## Dataset attribution

Ocean temperature observations from the **eMOLT** (Environmental Monitors on Lobster
Traps and Large Trawlers) program, retrieved via the ondeckdata ERDDAP server
(`erddap.ondeckdata.com`), covering 1-7 Aug 2024. Source metadata and license: [eMOLT ERDDAP info](https://erddap.ondeckdata.com/erddap/info/emolt_data/index.htmlTable) (free use and redistribution; not intended for legal use).


