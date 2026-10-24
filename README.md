# ShelfCast

**What if one more ocean temperature reading could change what we think is happening nearby?**

ShelfCast is my Hackachusetts 2026 Climate Tech project. It uses real [eMOLT](https://erddap.ondeckdata.com/erddap/info/emolt_data/index.htmlTable) temperature readings collected through fishing activity to estimate water temperature at different depths off Massachusetts. The app hides later measurements, asks the model to predict them, then lets you reveal one profile and see what changes. It also shows where five versions of the model disagree and suggests a later historical profile to test.

I wanted the model to face a real measurement it had not seen. The reveal makes its prediction, its mistakes, and the effect of new data visible in one place.

## Try the replay

1. Choose a candidate profile in the selector. The map shows where training and candidate profiles were recorded; the app shows the selected site's temperature prediction at 5, 10, 20, 30, and 50 metres, plus the range predicted by five models.
2. Click **Reveal actual measurements**. The real readings appear at their recorded depths. A temporary model learns from that one profile, and the app shows how its predictions change at the selected site and a nearby still-hidden site.
3. Look at **Suggested next measurement**. Among eligible later profiles, ShelfCast selects the one where the five models disagree most at 5 and 10 metres.
4. Click **Reset replay** or choose another profile to start again.

This is a **historical replay of August 2024**, not a live ocean forecast. The suggested profile is a place to test, not a proven optimal sampling location or a boat route.

## Why this could be useful

Ocean observations are uneven in space and time. A model can fill gaps on a map, but a clean-looking map does not tell us where more data would matter. ShelfCast makes that question concrete: what did the model predict before it saw a profile, how did one real profile change nearby estimates, and where do different fits still disagree?

A coastal research or community monitoring program could use a tested version of this idea to examine gaps in its observations. The hackathon build demonstrates the workflow. It does **not** establish that its suggested measurement improves accuracy; that requires a comparison with simple selection strategies on held-out profiles.

## What is under the hood

```text
eMOLT readings
  -> clean and group nearby readings into candidate profiles
  -> train on profiles ending before 6 August 2024
  -> predict later profiles without using their temperatures
  -> reveal one profile on click and refit in memory
  -> show the change and rank later candidates by model disagreement
```

The first predictor is a CPU-friendly scikit-learn ExtraTrees model. Its inputs are latitude, longitude, requested depth, and recorded UTC time. For the spread display, five versions of that same model are fit by resampling **whole training profiles**, not individual readings. The shaded minimum-to-maximum range is a way to inspect model disagreement; it is **not a calibrated confidence interval**.

The released starter data has 20,000 readings. The declared study area (41.5–42.5°N, 70.5–69.5°W) yields 105 retained candidate profiles: 61 training profiles (1,390 readings) and 44 later replay profiles (832 readings). The split is chronological, and no reading from a hidden profile is used for fitting until that profile is explicitly revealed. Updated models stay in memory and never overwrite the saved starting model.

The starter file lacks the identifiers needed to verify fishing tow or cast boundaries. The groups here are therefore **provisional candidate profiles** inferred from location and time. Prediction depths are requested levels; they do not claim to be the bottom depth at each site.

## Run the test build

The raw ZIP, generated splits, and trained model are intentionally absent from Git. From a clean clone, run the following from the repository root. Python 3.11 or newer is recommended.

```bash
python -m pip install -r requirements.txt
curl -L https://hackachusetts2026.vercel.app/kits/emolt.zip -o Data/raw/emolt.zip
python Scripts/prepare_data.py
python Scripts/split_replay.py
python Scripts/train_model.py
python -m streamlit run app.py
```

On Windows PowerShell, use `Invoke-WebRequest https://hackachusetts2026.vercel.app/kits/emolt.zip -OutFile Data/raw/emolt.zip` instead of the `curl` line. The repository includes `Data/raw/`; generated files are written under `Data/processed/`, `Data/splits/`, and `Results/`.

To run the checks:

```bash
python -m pytest
```

If you want to inspect the steps separately, `Scripts/prepare_data.py` builds the candidate profiles, `Scripts/split_replay.py` makes the chronological split, and `Scripts/train_model.py` fits the saved starting model. `app.py` is the interactive replay.

## How I used Kiro

I built ShelfCast in six scoped stages with the Kiro IDE. Each stage has requirements, a design, and implementation tasks in the root [`.kiro/specs/`](.kiro/specs/) folder. [Steering](.kiro/steering/shelfcast-purpose-scope.md) kept the constraints visible throughout development: use the real starter data, keep complete profiles on one side of the time split, never train on a hidden profile before reveal, and describe uncertainty and profile identity honestly.

The specs were useful because each stage had a checkable stopping point. Kiro helped implement the data pipeline, model, Streamlit viewer, reveal loop, and five-model spread; the tests under [`tests/`](tests/) check the split, model behavior, reveal boundary, and suggestion logic. The code and the decisions behind it are both in this repository.

## What I would test next

The next experiment is to hold out complete later profiles and compare prediction error with simple depth-aware and nearby-observation baselines. I would also compare disagreement-based measurement selection with random and coverage-based selection at the same measurement budget. Until those tests are run, ShelfCast is a working research prototype, not a validated operational ocean product.

## Data credit

Ocean temperature observations come from the [eMOLT program via ondeckdata ERDDAP](https://erddap.ondeckdata.com/erddap/info/emolt_data/index.htmlTable), covering 1–7 August 2024. The source metadata permits free use and redistribution and says the data is not intended for legal use. The starter ZIP is downloaded from the [Hackachusetts challenge site](https://hackachusetts2026.vercel.app/kits/emolt.zip).
