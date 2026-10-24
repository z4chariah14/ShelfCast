# ShelfCast

ShelfCast will eventually estimate coastal ocean temperature at different
depths and suggest where a new measurement would be most useful. This
repository currently contains **Stage 1: the data foundation only** — no
model, map, dashboard, or deployment.

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

## Tests

```
python -m pytest
```

Runtime code depends only on pandas and the Python standard library. Running
the tests additionally requires pytest.

## Dataset attribution

Ocean temperature observations from the **eMOLT** (Environmental Monitors on Lobster
Traps and Large Trawlers) program, retrieved via the ondeckdata ERDDAP server
(`erddap.ondeckdata.com`), covering 1-7 Aug 2024. Source metadata and license: [eMOLT ERDDAP info](https://erddap.ondeckdata.com/erddap/info/emolt_data/index.htmlTable) (free use and redistribution; not intended for legal use).


