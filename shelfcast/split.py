"""ShelfCast Stage 2 chronological replay split.

All Stage 2 logic lives in this single module as separate, well-named functions
so the flow stays easy to read while each stage is individually testable.
Runtime code uses pandas and the Python standard library only -- no numpy.

The failure guarantee is an ordering guarantee, not a transaction:
check_integrity runs ALL integrity checks first and raises before
write_split_outputs is ever called. On failure nothing is written and the CLI
exits non-zero. There is no file-publishing or rollback step.

Stage 1 groups are provisional CANDIDATE PROFILES inferred from recorded
position and time proximity -- never verified fishing tows or casts.
"""

from __future__ import annotations

import json
import os

import pandas as pd

from shelfcast.config import CANDIDATE_SITE_COLUMNS

POINT_COLUMNS = [
    "time",
    "latitude",
    "longitude",
    "depth_m",
    "temperature_c",
    "profile_id",
]


class IntegrityError(ValueError):
    """Raised when a hard-fail split integrity check fails.

    Subclasses ValueError so the CLI's ValueError catch handles it, while the
    name keeps the intent explicit at the call site.
    """


# --------------------------------------------------------------------------
# Load (Requirement 1.1, 1.2)
# --------------------------------------------------------------------------
def load_stage1_outputs(processed_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read profile_summary.csv and profile_points.csv as tz-aware UTC frames.

    Parses summary start_time/end_time and points time with
    pd.to_datetime(..., utc=True) so all comparisons against the cutoff are
    timezone-aware. Raises FileNotFoundError naming the missing path when either
    file is absent.
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


# --------------------------------------------------------------------------
# Classify (Requirement 2)
# --------------------------------------------------------------------------
def classify_profiles(summary_df: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Assign each profile_id a single whole-profile label.

    end_time < cutoff            -> train
    start_time >= cutoff         -> heldout
    otherwise (start < cutoff <= end, includes end == cutoff) -> excluded

    The three conditions are mutually exclusive and total.
    """

    def label_for(row) -> str:
        start, end = row["start_time"], row["end_time"]
        if end < cutoff:
            return "train"
        if start >= cutoff:
            return "heldout"
        return "excluded"

    out = summary_df[["profile_id", "start_time", "end_time"]].copy()
    out["label"] = summary_df.apply(label_for, axis=1)
    return out


# --------------------------------------------------------------------------
# Integrity checks (Requirement 6) -- all run before any write
# --------------------------------------------------------------------------
def check_integrity(
    summary_df: pd.DataFrame,
    points_df: pd.DataFrame,
    classification: pd.DataFrame,
    train_points: pd.DataFrame,
    heldout_points: pd.DataFrame,
) -> None:
    """Run every hard-fail check in order; raise IntegrityError on first failure.

    Leakage is id-based, not value-based: identical measured temperature or
    depth values appearing in both point files are normal and are NOT leakage.
    What must never happen is a profile's readings being split across sets.
    """
    # (a) summary / points profile_id sets must match exactly -- Req 6.2
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
    bounds = points_df.groupby("profile_id")["time"].agg(["min", "max"])
    mismatched = []
    for _, row in summary_df.iterrows():
        pid = row["profile_id"]
        pmin = bounds.loc[pid, "min"]
        pmax = bounds.loc[pid, "max"]
        if row["start_time"] != pmin or row["end_time"] != pmax:
            mismatched.append(int(pid))
    if mismatched:
        raise IntegrityError(
            "summary start_time/end_time does not match points time range "
            f"for profile_id(s): {sorted(set(mismatched))}"
        )

    # (d) train and heldout id sets must be disjoint -- Req 6.6
    train_ids = set(
        classification.loc[classification["label"] == "train", "profile_id"]
    )
    heldout_ids = set(
        classification.loc[classification["label"] == "heldout", "profile_id"]
    )
    overlap = train_ids & heldout_ids
    if overlap:
        raise IntegrityError(
            f"train/heldout profile_id overlap: {sorted(overlap)}"
        )

    # (e) id-based membership of the point frames -- Req 6.5
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


# --------------------------------------------------------------------------
# Candidate sites (Requirement 4) -- structural column guard by construction
# --------------------------------------------------------------------------
def build_candidate_sites(summary_df: pd.DataFrame, heldout_ids) -> pd.DataFrame:
    """Heldout profiles only, columns exactly CANDIDATE_SITE_COLUMNS.

    Projecting onto CANDIDATE_SITE_COLUMNS drops end_time, temperature, depth,
    and every other summary measurement column by construction (Req 4.3, 6.7).
    """
    rows = summary_df[summary_df["profile_id"].isin(set(heldout_ids))]
    sites = rows[CANDIDATE_SITE_COLUMNS].copy()
    return sites.reset_index(drop=True)


# --------------------------------------------------------------------------
# Report (Requirement 5)
# --------------------------------------------------------------------------
def build_split_report(
    classification: pd.DataFrame, points_df: pd.DataFrame, cutoff
) -> dict:
    """Assemble the split_report.json dict (counts, time ranges, excluded list)."""
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


# --------------------------------------------------------------------------
# Write outputs (Requirement 3, 4, 5) -- final column guard before any write
# --------------------------------------------------------------------------
def _write_points(path: str, points: pd.DataFrame) -> None:
    """Write a points frame; ISO 8601 time, header-only CSV when empty."""
    out = points.copy()
    if "time" in out.columns and len(out) > 0:
        out["time"] = out["time"].map(
            lambda t: t.isoformat() if pd.notna(t) else ""
        )
    if len(out) == 0:
        out = pd.DataFrame(columns=POINT_COLUMNS)
    out.to_csv(path, index=False)


def write_split_outputs(
    splits_dir: str,
    train_points: pd.DataFrame,
    heldout_points: pd.DataFrame,
    candidate_sites: pd.DataFrame,
    report: dict,
) -> None:
    """Create splits_dir and write the four Stage 2 artifacts.

    Performs the final structural candidate-sites column guard (Req 6.7) before
    any write, so a compromised candidate_sites frame stops the write with
    nothing written.
    """
    if list(candidate_sites.columns) != CANDIDATE_SITE_COLUMNS:
        raise IntegrityError(
            "candidate_sites columns must be exactly "
            f"{CANDIDATE_SITE_COLUMNS}, got {list(candidate_sites.columns)}"
        )
    forbidden = [
        c
        for c in candidate_sites.columns
        if c == "temperature_c"
        or c.startswith("temp_")
        or c == "depth_m"
        or c.startswith("depth_")
        or c == "end_time"
    ]
    if forbidden:
        raise IntegrityError(
            f"candidate_sites leaks hidden columns: {forbidden}"
        )

    os.makedirs(splits_dir, exist_ok=True)

    _write_points(os.path.join(splits_dir, "train_points.csv"), train_points)
    _write_points(os.path.join(splits_dir, "heldout_points.csv"), heldout_points)
    candidate_sites.to_csv(
        os.path.join(splits_dir, "candidate_sites.csv"), index=False
    )
    with open(
        os.path.join(splits_dir, "split_report.json"), "w", encoding="utf-8"
    ) as fh:
        json.dump(report, fh, indent=2)


__all__ = [
    "IntegrityError",
    "POINT_COLUMNS",
    "load_stage1_outputs",
    "classify_profiles",
    "check_integrity",
    "build_candidate_sites",
    "build_split_report",
    "write_split_outputs",
]
