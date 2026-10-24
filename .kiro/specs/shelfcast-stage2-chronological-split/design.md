# Design Document

## Overview

Stage 2 adds a chronological replay split on top of the Stage 1 data
foundation. The `Split_Tool` reads the two Stage 1 processed artifacts, labels
each **candidate profile** as a whole against a fixed UTC cutoff, runs hard-fail
integrity checks, and — only if those checks pass — writes four local,
git-ignored artifacts under `Data/splits/`.

The failure guarantee is simple and relies on ordering, not on any transaction
mechanism: `check_integrity` runs **all** integrity checks first and raises
before `write_split_outputs` is ever called. The CLI maps that exception to a
non-zero exit. Because nothing is written until every check has already passed,
a failed run writes no split files. There is no file-publishing, transaction, or
rollback mechanism, and none is needed for this MVP.

The design mirrors Stage 1 conventions exactly:

- A thin CLI (`Scripts/split_replay.py`) with `argparse`, a one-line success
  summary, and a `try/except` that maps a fixed set of exceptions to a stderr
  message plus non-zero exit (Req 7).
- A single testable module (`shelfcast/split.py`) holding all logic as separate,
  well-named functions, using **pandas and the Python standard library only —
  no numpy** (Req 7, 8).
- Additive constants appended to `shelfcast/config.py`. All existing Stage 1
  constants and all Stage 1 behavior (`config.py`, `pipeline.py`,
  `prepare_data.py`) remain unchanged (additive-only).

The Stage 1 groups remain **provisional candidate profiles** inferred from
recorded position and time proximity. No output or doc uses the words "tow",
"cast", or "segment type" (Req 10).

### In Scope

- Classify candidate profiles against the cutoff (whole-profile).
- Write `train_points.csv`, `heldout_points.csv`, `candidate_sites.csv`,
  `split_report.json`.
- Hard-fail integrity checks that all complete before any write; on failure,
  nothing is written and the process exits non-zero.
- CLI, focused tests, README/`.gitignore`/steering updates.

### Out of Scope (explicit)

- Any predictive or interpolation model.
- Any map or spatial visualization.
- Any dashboard or UI.
- Any deployment or hosting.
- Any rewrite of Stage 1 code. All Stage 1 behavior in `config.py`,
  `pipeline.py`, and `prepare_data.py` remains unchanged; the only change to
  Stage 1 files is additive constants appended to `config.py`.
- Any change to the Stage 1 study region.

## Architecture

```
Scripts/split_replay.py        (thin CLI; argparse; one-line summary; exit codes)
        |
        v
shelfcast/split.py             (all Stage 2 logic; pandas + stdlib only)
   load_stage1_outputs
   classify_profiles
   check_integrity             <-- runs ALL checks; raises BEFORE any write
   build_candidate_sites
   build_split_report
   write_split_outputs         <-- only reached when every check has passed
        |
        v
shelfcast/config.py            (additive Stage 2 constants; Stage 1 unchanged)
```

`check_integrity` is the single place that runs every integrity check: (a)
summary/points `profile_id`-set match, (b) no duplicate summary `profile_id`,
(c) summary `start_time`/`end_time` equal per-profile points min/max `time`,
(d) train/heldout `profile_id` sets disjoint, and (e) train-only / heldout-only
`profile_id` membership for the point frames. Because all five run before
`write_split_outputs` is called, any failure stops the run with nothing written
and a non-zero exit. The structural `candidate_sites` column guard lives where
`candidate_sites` is built and is re-asserted immediately before that file is
written.

Data flow:

```
Data/processed/profile_summary.csv  --+
Data/processed/profile_points.csv   --+--> load_stage1_outputs
                                          -> classify_profiles (summary only)
                                          -> check_integrity (raise, or continue)
                                          -> build_candidate_sites (heldout)
                                          -> build_split_report
                                          -> write_split_outputs
                                             -> Data/splits/train_points.csv
                                             -> Data/splits/heldout_points.csv
                                             -> Data/splits/candidate_sites.csv
                                             -> Data/splits/split_report.json
```

### Configuration decision: additive constants in `shelfcast/config.py`

**Chosen approach: append Stage 2 constants to `shelfcast/config.py`.** Stage 1
already treats `config.py` as a logic-free home for named constants, so a single
constants module stays consistent with the established convention and avoids a
second config file. The change is strictly additive: all existing Stage 1
constants and all Stage 1 behavior in `config.py`, `pipeline.py`, and
`prepare_data.py` remain unchanged, and no existing Stage 1 constant is touched.
This satisfies Req 1.3, which requires Stage 2 constants to be added additively
and all Stage 1 constants and behavior to remain unchanged.

The following block is appended to `shelfcast/config.py` (Stage 1 lines above it
are left exactly as-is):

```python
# --------------------------------------------------------------------------
# Stage 2 chronological-split constants (additive; Stage 1 above is unchanged)
# --------------------------------------------------------------------------
from datetime import datetime, timezone

# Fixed replay cutoff -- Requirement 2.1
CUTOFF = datetime(2024, 8, 6, 0, 0, 0, tzinfo=timezone.utc)

PROCESSED_DIR = "Data/processed"      # Stage 1 outputs (Stage 2 input)
SPLITS_DIR = "Data/splits"            # Stage 2 outputs

# Candidate_Sites columns -- exactly these four, in this order (Req 4.1)
CANDIDATE_SITE_COLUMNS = ["profile_id", "latitude", "longitude", "start_time"]
```

## Components and Interfaces

All functions live in `shelfcast/split.py`. Signatures use the `from
__future__ import annotations` style used in Stage 1.

### `load_stage1_outputs(processed_dir) -> (summary_df, points_df)`

Reads the two Stage 1 CSVs and parses timestamps as tz-aware UTC (Req 1.1, 1.2).

```python
def load_stage1_outputs(processed_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read profile_summary.csv and profile_points.csv.

    Parses start_time/end_time (summary) and time (points) with
    pd.to_datetime(..., utc=True) so all comparisons against CUTOFF are
    timezone-aware. Raises FileNotFoundError if either file is missing.
    """
    summary_path = os.path.join(processed_dir, "profile_summary.csv")
    points_path = os.path.join(processed_dir, "profile_points.csv")
    for path in (summary_path, points_path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Stage 1 output not found: {path}")

    summary_df = pd.read_csv(summary_path)
    points_df = pd.read_csv(points_path)

    for col in ("start_time", "end_time"):
        summary_df[col] = pd.to_datetime(summary_df[col], utc=True)
    points_df["time"] = pd.to_datetime(points_df["time"], utc=True)
    return summary_df, points_df
```

If a required column is absent, the `KeyError` from the column access surfaces
to the CLI, which maps it to a non-zero exit (Req 6, 7).

### `classify_profiles(summary_df, cutoff) -> classification`

Labels each profile **as a whole** using summary `start_time`/`end_time`
(Req 2.2-2.5). Returns a frame with one row per `profile_id` and a `label`
column taking `"train"`, `"heldout"`, or `"excluded"`.

Boundary rules (Req 2):

| Condition                                        | Label      | Req  |
| ------------------------------------------------ | ---------- | ---- |
| `end_time < cutoff`                              | `train`    | 2.2  |
| `start_time >= cutoff`                           | `heldout`  | 2.3  |
| `start_time < cutoff <= end_time`                | `excluded` | 2.4  |
| `end_time == cutoff` exactly                     | `excluded` | 2.5  |

Note that `end_time == cutoff` falls out of the general rules: it is not
`end_time < cutoff` (so not train) and, for a profile that starts before the
cutoff, satisfies `start_time < cutoff <= end_time` (so excluded). A profile
that both starts and ends exactly at the cutoff is `heldout` via `start_time >=
cutoff`, consistent with Req 2.3. The three conditions are mutually exclusive
and total.

```python
def classify_profiles(summary_df: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Assign each profile_id a single label: train / heldout / excluded."""
    def label_for(row) -> str:
        start, end = row["start_time"], row["end_time"]
        if end < cutoff:
            return "train"
        if start >= cutoff:
            return "heldout"
        return "excluded"   # start < cutoff <= end  (includes end == cutoff)

    out = summary_df[["profile_id", "start_time", "end_time"]].copy()
    out["label"] = summary_df.apply(label_for, axis=1)
    return out
```

Point rows never carry their own label; they follow their profile by joining on
`profile_id` (Req 2.6), done inside `write_split_outputs`/`build_split_report`.

### `check_integrity(summary_df, points_df, classification) -> None`

Runs **all** the hard-fail checks and raises before any file is written
(Req 6.1). Because every check completes here and `write_split_outputs` is only
reached after `check_integrity` returns, a failure leaves `Data/splits/`
untouched — no transaction or rollback is involved, just ordering.

Leakage is **id-based, not value-based.** Identical temperature or depth values
appearing in both the train and heldout point files are normal and are not
leakage; what must never happen is a profile's readings being split across sets.
So the point-frame checks assert membership on `profile_id`, never on measured
values.

A dedicated exception type makes the CLI mapping explicit:

```python
class IntegrityError(ValueError):
    """Raised when a hard-fail split integrity check fails.

    Subclasses ValueError so the CLI's ValueError catch handles it, while the
    name keeps the intent explicit at the call site.
    """
```

`check_integrity` runs these checks in order and raises on the first failure:

```python
def check_integrity(summary_df, points_df, classification,
                    train_points, heldout_points) -> None:
    # (a) summary/points profile_id sets must match exactly -- Req 6.2
    summary_ids = set(summary_df["profile_id"])
    points_ids = set(points_df["profile_id"])
    if summary_ids != points_ids:
        only_summary = sorted(summary_ids - points_ids)
        only_points = sorted(points_ids - summary_ids)
        raise IntegrityError(
            "profile_id mismatch between summary and points: "
            f"only_in_summary={only_summary} only_in_points={only_points}"
        )

    # (b) no duplicate profile_id in summary -- Req 6.3
    dup_counts = summary_df["profile_id"].value_counts()
    duplicates = sorted(int(pid) for pid, n in dup_counts.items() if n > 1)
    if duplicates:
        raise IntegrityError(
            f"duplicate profile_id values in profile_summary: {duplicates}"
        )

    # (c) summary start/end must equal per-profile points min/max time -- Req 6.4
    # Compute per-profile min/max from points_df and compare tz-aware against
    # the summary timestamps. This makes the cutoff assignment trustworthy:
    # classification uses summary start_time/end_time, so those bounds must
    # actually match the readings they claim to summarize.
    bounds = points_df.groupby("profile_id")["time"].agg(["min", "max"])
    summary_indexed = summary_df.set_index("profile_id")
    mismatched = []
    for pid, row in summary_indexed.iterrows():
        pmin = bounds.loc[pid, "min"]
        pmax = bounds.loc[pid, "max"]
        if row["start_time"] != pmin or row["end_time"] != pmax:
            mismatched.append(int(pid))
    if mismatched:
        raise IntegrityError(
            "summary start_time/end_time does not match points time range "
            f"for profile_id(s): {sorted(mismatched)}"
        )

    # (d) train and heldout id sets must be disjoint -- Req 6.6
    train_ids = set(classification.loc[classification["label"] == "train", "profile_id"])
    heldout_ids = set(classification.loc[classification["label"] == "heldout", "profile_id"])
    overlap = train_ids & heldout_ids
    if overlap:
        raise IntegrityError(f"train/heldout profile_id overlap: {sorted(overlap)}")

    # (e) point-frame membership is id-based -- Req 6.5
    #     every train_points row has a profile_id in the train set; every
    #     heldout_points row has a profile_id in the heldout set.
    bad_train = sorted(set(train_points["profile_id"]) - train_ids)
    if bad_train:
        raise IntegrityError(
            f"train_points rows carry non-train profile_id(s): {bad_train}"
        )
    bad_heldout = sorted(set(heldout_points["profile_id"]) - heldout_ids)
    if bad_heldout:
        raise IntegrityError(
            f"heldout_points rows carry non-heldout profile_id(s): {bad_heldout}"
        )
```

The structural candidate-sites column guard (Req 6.7) is enforced where
`candidate_sites` is built (`build_candidate_sites`) and re-asserted in
`write_split_outputs` immediately before the file is written (see below), so no
measurement column can ever reach disk. That guard is a pure structural column
check — exactly `profile_id, latitude, longitude, start_time`, with no
`temperature`/`depth`/`end_time`/summary measurement column present.

### `build_candidate_sites(summary_df, heldout_ids) -> frame`

Builds the heldout-only sites frame with **exactly** the four allowed columns in
the configured order (Req 4.1-4.3).

```python
def build_candidate_sites(summary_df: pd.DataFrame, heldout_ids) -> pd.DataFrame:
    """Heldout profiles only, columns exactly CANDIDATE_SITE_COLUMNS."""
    rows = summary_df[summary_df["profile_id"].isin(set(heldout_ids))]
    sites = rows[CANDIDATE_SITE_COLUMNS].copy()   # projection drops everything else
    return sites.reset_index(drop=True)
```

By projecting onto `CANDIDATE_SITE_COLUMNS`, `end_time`, `temperature_c`,
`depth_*`, and every summary measurement column are dropped by construction
(Req 4.3). The guard in `write_split_outputs` verifies this before writing.

### `build_split_report(classification, points_df, cutoff) -> dict`

Assembles the report dict (Req 5). Point counts come from joining points to the
classification on `profile_id`.

```python
def build_split_report(classification, points_df, cutoff) -> dict:
    labeled_points = points_df.merge(
        classification[["profile_id", "label"]], on="profile_id", how="left"
    )

    def set_stats(label: str) -> dict:
        prof = classification[classification["label"] == label]
        pts = labeled_points[labeled_points["label"] == label]
        if len(prof) > 0:
            time_range = {
                "start_min": prof["start_time"].min().isoformat(),
                "end_max": prof["end_time"].max().isoformat(),
            }
        else:
            time_range = {"start_min": None, "end_max": None}
        return {
            "profile_count": int(len(prof)),
            "point_count": int(len(pts)),
            "time_range": time_range,
        }

    excluded = classification[classification["label"] == "excluded"]
    excluded_list = [
        {
            "profile_id": int(r["profile_id"]),
            "start_time": r["start_time"].isoformat(),
            "end_time": r["end_time"].isoformat(),
        }
        for _, r in excluded.iterrows()
    ]

    return {
        "cutoff": cutoff.isoformat(),
        "train": set_stats("train"),
        "heldout": set_stats("heldout"),
        "excluded": set_stats("excluded"),
        "excluded_profiles": excluded_list,
        "integrity_note": (
            "Groups are provisional candidate profiles inferred from recorded "
            "position and time proximity; they are NOT verified fishing tows "
            "or casts."
        ),
    }
```

### `write_split_outputs(splits_dir, train_points, heldout_points, candidate_sites, report) -> None`

Creates `Data/splits/` and writes the four artifacts (Req 3, 4, 5). It performs
the final structural candidate-sites column guard (Req 6.7) before writing
anything, so a compromised `candidate_sites` frame stops the write with nothing
written.

```python
def write_split_outputs(
    splits_dir: str,
    train_points: pd.DataFrame,
    heldout_points: pd.DataFrame,
    candidate_sites: pd.DataFrame,
    report: dict,
) -> None:
    # Final structural column guard -- Req 6.7 (runs before any write).
    if list(candidate_sites.columns) != CANDIDATE_SITE_COLUMNS:
        raise IntegrityError(
            "candidate_sites columns must be exactly "
            f"{CANDIDATE_SITE_COLUMNS}, got {list(candidate_sites.columns)}"
        )
    forbidden = [
        c for c in candidate_sites.columns
        if c == "temperature_c" or c.startswith("temp_") or c == "depth_m"
        or c.startswith("depth_") or c == "end_time"
    ]
    if forbidden:
        raise IntegrityError(f"candidate_sites leaks hidden columns: {forbidden}")

    os.makedirs(splits_dir, exist_ok=True)

    _write_points(os.path.join(splits_dir, "train_points.csv"), train_points)
    _write_points(os.path.join(splits_dir, "heldout_points.csv"), heldout_points)
    candidate_sites.to_csv(
        os.path.join(splits_dir, "candidate_sites.csv"), index=False
    )
    with open(os.path.join(splits_dir, "split_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
```

`_write_points` serializes the `time` column as ISO 8601 and writes
header-only CSVs for empty sets (mirrors Stage 1 `write_outputs`):

```python
POINT_COLUMNS = ["time", "latitude", "longitude", "depth_m", "temperature_c", "profile_id"]

def _write_points(path: str, points: pd.DataFrame) -> None:
    out = points.copy()
    if "time" in out.columns and len(out) > 0:
        out["time"] = out["time"].map(lambda t: t.isoformat() if pd.notna(t) else "")
    if len(out) == 0:
        out = pd.DataFrame(columns=POINT_COLUMNS)
    out.to_csv(path, index=False)
```

### `Scripts/split_replay.py` (thin CLI)

Mirrors `Scripts/prepare_data.py`: inserts the project root on `sys.path`,
parses args, orchestrates the module functions, maps a fixed exception set to a
stderr message plus exit code 1, and prints a one-line summary on success
(Req 7).

```python
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ShelfCast Stage 2 chronological split")
    parser.add_argument("--processed", default=PROCESSED_DIR)
    parser.add_argument("--output", "--splits", dest="output", default=SPLITS_DIR)
    args = parser.parse_args(argv)

    try:
        summary_df, points_df = split.load_stage1_outputs(args.processed)
        classification = split.classify_profiles(summary_df, CUTOFF)

        labeled = points_df.merge(
            classification[["profile_id", "label"]], on="profile_id", how="left"
        )
        train_points = labeled[labeled["label"] == "train"][POINT_COLUMNS]
        heldout_points = labeled[labeled["label"] == "heldout"][POINT_COLUMNS]

        # All integrity checks run here, before any write.
        split.check_integrity(
            summary_df, points_df, classification, train_points, heldout_points
        )

        heldout_ids = classification.loc[
            classification["label"] == "heldout", "profile_id"
        ]
        candidate_sites = split.build_candidate_sites(summary_df, heldout_ids)
        report = split.build_split_report(classification, points_df, CUTOFF)
        split.write_split_outputs(
            args.output, train_points, heldout_points, candidate_sites, report
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        # IntegrityError subclasses ValueError, so it is caught here too.
        print(f"Stage 2 split failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Stage 2 split complete: "
        f"train={report['train']['profile_count']} "
        f"heldout={report['heldout']['profile_count']} "
        f"excluded={report['excluded']['profile_count']} "
        f"(profiles); outputs written to {args.output}"
    )
    return 0
```

## Data Models

### Classification frame (in-memory)

| Column       | Type              | Notes                                  |
| ------------ | ----------------- | -------------------------------------- |
| `profile_id` | int               | One row per Stage 1 candidate profile  |
| `start_time` | tz-aware datetime | From summary                           |
| `end_time`   | tz-aware datetime | From summary                           |
| `label`      | str               | `train` \| `heldout` \| `excluded`     |

### Output artifacts (`Data/splits/`)

| File                  | Columns / shape                                                      | Req   |
| --------------------- | ------------------------------------------------------------------- | ----- |
| `train_points.csv`    | `time, latitude, longitude, depth_m, temperature_c, profile_id`     | 3.1   |
| `heldout_points.csv`  | `time, latitude, longitude, depth_m, temperature_c, profile_id`     | 3.2   |
| `candidate_sites.csv` | exactly `profile_id, latitude, longitude, start_time`               | 4.1-4.3 |
| `split_report.json`   | see structure below                                                 | 5     |

Timestamps are serialized as ISO 8601 strings via `to_csv(index=False)`. Empty
sets produce header-only CSVs.

### `split_report.json` structure

```json
{
  "cutoff": "2024-08-06T00:00:00+00:00",
  "train":    {"profile_count": 0, "point_count": 0, "time_range": {"start_min": null, "end_max": null}},
  "heldout":  {"profile_count": 0, "point_count": 0, "time_range": {"start_min": null, "end_max": null}},
  "excluded": {"profile_count": 0, "point_count": 0, "time_range": {"start_min": null, "end_max": null}},
  "excluded_profiles": [
    {"profile_id": 0, "start_time": "...", "end_time": "..."}
  ],
  "integrity_note": "Groups are provisional candidate profiles ..."
}
```

`time_range` is `{start_min, end_max}` per set, with both `null` when the set is
empty (Req 5.3). `excluded_profiles` lists each excluded id with its times
(Req 5.4). `cutoff` is the ISO string of `CUTOFF` (Req 5.5).

## Error Handling

All integrity checks complete before any write. On failure, nothing is written
and the process exits non-zero: `check_integrity` raises before
`write_split_outputs` is ever called, and the CLI maps that exception to a
stderr message and exit code 1, mirroring Stage 1. This is an ordering
guarantee, not a transaction — there is no file-publishing or rollback step,
and none is needed for this MVP.

| Condition                                               | Raised by                      | Exception          | CLI behavior                  | Req      |
| ------------------------------------------------------- | ------------------------------ | ------------------ | ----------------------------- | -------- |
| `profile_summary.csv` or `profile_points.csv` missing   | `load_stage1_outputs`          | `FileNotFoundError`| stderr + exit 1               | 1.1, 7   |
| Required column absent in a Stage 1 CSV                  | `load_stage1_outputs` / access | `KeyError`         | stderr + exit 1               | 6, 7     |
| `summary` vs `points` `profile_id` sets differ          | `check_integrity`              | `IntegrityError`   | no write, stderr + exit 1     | 6.2      |
| Duplicate `profile_id` in `profile_summary`             | `check_integrity`              | `IntegrityError`   | no write, stderr + exit 1     | 6.3      |
| Summary `start_time`/`end_time` ≠ points min/max `time` | `check_integrity`              | `IntegrityError`   | no write, stderr + exit 1     | 6.4      |
| `train`/`heldout` id sets overlap                       | `check_integrity`              | `IntegrityError`   | no write, stderr + exit 1     | 6.6      |
| A point row carries a non-matching-set `profile_id`     | `check_integrity`              | `IntegrityError`   | no write, stderr + exit 1     | 6.5      |
| `candidate_sites` carries a non-allowed column          | `write_split_outputs` guard    | `IntegrityError`   | no write, stderr + exit 1     | 6.7      |
| Unparseable timestamp / other value error              | pandas / module                | `ValueError`       | stderr + exit 1               | 7        |
| All checks pass                                         | —                              | —                  | write 4 artifacts, exit 0     | 6.8, 7.3 |

`IntegrityError` subclasses `ValueError`, so the CLI's
`except (FileNotFoundError, KeyError, ValueError)` already catches it while the
name keeps the intent explicit in the module.

## Testing Strategy

Focused example-based pytest in `tests/test_split.py`, using **pandas and the
Python standard library only — no numpy** (Req 8.1), consistent with the Stage 1
test style. Tests construct small in-memory summary/points frames (or write tiny
CSVs to a `tmp_path`) and assert on classification, written files, and failure
behavior (on failure nothing is written). No formal Correctness Properties
section is included; Stage 2 follows Stage 1's focused-example approach.

The boundary-classification tests and the leakage/column tests below are
**required** — they verify mandatory split behaviors, not optional coverage.

Required tests:

1. **Cutoff boundary classification (Req 8.2, 2.2-2.5) — required.** Build
   profiles with `end_time < cutoff` (expect `train`), `start_time >= cutoff`
   (expect `heldout`), and `end_time == cutoff` exactly (expect `excluded`);
   assert each label.
2. **Spanning profile excluded (Req 8.3, 2.4).** A profile with `start_time <
   cutoff` and `end_time > cutoff` is labeled `excluded`.
3. **Whole-profile separation (Req 8.4, 2.6).** After a full run, gather every
   `(profile_id, point)` across `train_points.csv` and `heldout_points.csv` and
   assert every point appears in exactly one set and never both; no profile's
   `profile_id` appears in more than one points file.
4. **ID-based leakage membership (Req 8.6, 6.5, 6.6) — required.** After a full
   run, assert every `profile_id` in `train_points.csv` is a Training_Set id,
   every `profile_id` in `heldout_points.csv` is a Heldout_Set id, and the two
   id sets are disjoint. This is an id-set check: identical measured temperature
   or depth values may appear in both files and are **not** treated as leakage.
5. **Candidate-sites structural columns (Req 8.5, 4.3, 6.7) — required.** Assert
   `candidate_sites.csv` columns are exactly `profile_id, latitude, longitude,
   start_time` (no `temperature_c`, `depth_*`, `temp_*`, `end_time`, or any
   summary measurement column).
6. **Duplicate summary row aborts without writing (Req 8.7, 6.3).** A
   `profile_summary` with a duplicated `profile_id` causes an `IntegrityError`
   (non-zero exit) AND leaves `Data/splits/` with none of the four artifacts.
7. **Summary/points time mismatch aborts without writing (Req 8.8, 6.4).** A
   profile whose summary `start_time` or `end_time` does not equal the earliest
   or latest points `time` for that `profile_id` causes an `IntegrityError`
   (non-zero exit) AND leaves `Data/splits/` with none of the four artifacts.
8. **Summary/points id-set mismatch aborts without writing (Req 6.2).** Feed a
   `profile_id` present in summary but absent from points (and vice versa);
   assert `IntegrityError` and that none of the four artifacts are written.
9. **Empty-set handling.** A classification with an empty set writes a
   header-only CSV and records `null` time ranges in the report.

Each test targets a single behavior; property-based testing is intentionally not
used, matching Stage 1 and the focused-test requirement (Req 8).

## Documentation and Repository Hygiene

These changes accompany the implementation (Req 9, 10):

- **README** gains a Stage 2 section with the exact regenerate command
  (`python Scripts/split_replay.py`) and a note that outputs are provisional
  candidate profiles (Req 9.1, 10.1).
- **`.gitignore`** adds `Data/splits/` (Req 9.2).
- **Steering** states "Stage 1 complete; Stage 2 active" while preserving the
  provisional-candidate rule (Req 9.3).
- The **`.kiro` directory stays tracked** in version control (Req 9.4).
- All outputs and docs use "candidate profile" and contain no tow/cast/
  segment-type label (Req 10.1, 10.2).
