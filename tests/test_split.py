"""Focused tests for the Stage 2 chronological replay split.

Uses pytest with pandas and the Python standard library only -- no numpy.
Covers cutoff-boundary classification, spanning exclusion, whole-profile
separation, id-based leakage membership, candidate-sites structural columns,
and the hard-fail integrity checks (which must leave Data/splits/ untouched).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import split
from shelfcast.config import CANDIDATE_SITE_COLUMNS, CUTOFF

ARTIFACTS = [
    "train_points.csv",
    "heldout_points.csv",
    "candidate_sites.csv",
    "split_report.json",
]


# --------------------------------------------------------------------------
# Builders for small in-memory summary / points frames
# --------------------------------------------------------------------------
def _profile_points(profile_id, start, n=3, step_seconds=30, lat=42.0, lon=-70.0):
    """n readings for one profile, 30 s apart, with a 10 m depth range."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "time": start + timedelta(seconds=step_seconds * i),
                "latitude": lat,
                "longitude": lon,
                "depth_m": round(10.0 * i / (n - 1), 4) if n > 1 else 0.0,
                "temperature_c": 12.0,
                "profile_id": profile_id,
            }
        )
    return rows


def _frames(specs):
    """Build (summary_df, points_df) from specs: (profile_id, start, n).

    Summary start_time/end_time are the true earliest/latest point times so the
    time-consistency integrity check passes for well-formed inputs.
    """
    point_rows, summary_rows = [], []
    for pid, start, n in specs:
        pts = _profile_points(pid, start, n=n)
        point_rows.extend(pts)
        times = [r["time"] for r in pts]
        summary_rows.append(
            {
                "profile_id": pid,
                "latitude": pts[0]["latitude"],
                "longitude": pts[0]["longitude"],
                "start_time": min(times),
                "end_time": max(times),
            }
        )
    summary_df = pd.DataFrame(summary_rows)
    points_df = pd.DataFrame(point_rows)
    return summary_df, points_df


def _run_full(tmp_path, summary_df, points_df):
    """Mimic the CLI orchestration end-to-end into tmp_path."""
    classification = split.classify_profiles(summary_df, CUTOFF)
    labeled = points_df.merge(
        classification[["profile_id", "label"]], on="profile_id", how="left"
    )
    train_points = labeled[labeled["label"] == "train"][split.POINT_COLUMNS]
    heldout_points = labeled[labeled["label"] == "heldout"][split.POINT_COLUMNS]
    split.check_integrity(
        summary_df, points_df, classification, train_points, heldout_points
    )
    heldout_ids = classification.loc[
        classification["label"] == "heldout", "profile_id"
    ]
    candidate_sites = split.build_candidate_sites(summary_df, heldout_ids)
    report = split.build_split_report(classification, points_df, CUTOFF)
    out = str(tmp_path / "splits")
    split.write_split_outputs(
        out, train_points, heldout_points, candidate_sites, report
    )
    return out


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_PROJECT_ROOT, "Scripts", "split_replay.py")


def _write_stage1_csvs(processed_dir, summary_df, points_df):
    """Write summary/points frames to a temp Stage 1 processed directory.

    Timestamps are serialized as ISO 8601 so the CLI re-parses them the same way
    it parses the real Stage 1 outputs.
    """
    os.makedirs(processed_dir, exist_ok=True)
    s = summary_df.copy()
    for col in ("start_time", "end_time"):
        s[col] = s[col].map(lambda t: t.isoformat())
    p = points_df.copy()
    p["time"] = p["time"].map(lambda t: t.isoformat())
    s.to_csv(os.path.join(processed_dir, "profile_summary.csv"), index=False)
    p.to_csv(os.path.join(processed_dir, "profile_points.csv"), index=False)


def _run_cli(processed_dir, output_dir):
    """Run Scripts/split_replay.py as a real subprocess; return CompletedProcess."""
    return subprocess.run(
        [sys.executable, _CLI, "--processed", processed_dir, "--output", output_dir],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )


def _assert_aborted_cli(tmp_path, summary_df, points_df, expected_in_message):
    """Run the CLI on malformed input; assert exit 1, a useful message, no files."""
    processed = str(tmp_path / "processed")
    output = str(tmp_path / "splits")
    _write_stage1_csvs(processed, summary_df, points_df)

    result = _run_cli(processed, output)

    # Exit code 1 and a useful error message on stderr.
    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}; stderr={result.stderr!r}"
    )
    message = result.stderr.strip()
    assert message, "expected a non-empty error message on stderr"
    assert "Stage 2 split failed" in message
    for fragment in expected_in_message:
        assert fragment in message, (
            f"expected {fragment!r} in error message, got {message!r}"
        )

    # No split artifacts written (nothing before the aborting check).
    for name in ARTIFACTS:
        assert not os.path.exists(os.path.join(output, name)), (
            f"{name} must not be written on a failed integrity check"
        )


BEFORE = CUTOFF - timedelta(hours=2)   # fully before the cutoff
AFTER = CUTOFF + timedelta(hours=2)    # fully at/after the cutoff


# --------------------------------------------------------------------------
# Cutoff boundary classification (Req 8.2) -- required
# --------------------------------------------------------------------------
def test_cutoff_boundary_classification():
    # train: end_time < cutoff
    summary_df, _ = _frames([(0, BEFORE, 3)])
    cls = split.classify_profiles(summary_df, CUTOFF)
    assert cls.loc[cls["profile_id"] == 0, "label"].iloc[0] == "train"

    # heldout: start_time >= cutoff (start exactly at cutoff)
    summary_df, _ = _frames([(1, CUTOFF, 3)])
    cls = split.classify_profiles(summary_df, CUTOFF)
    assert cls.loc[cls["profile_id"] == 1, "label"].iloc[0] == "heldout"

    # excluded: end_time == cutoff exactly (starts before)
    summary_df, _ = _frames([(2, CUTOFF - timedelta(seconds=60), 3)])
    # force end_time to equal the cutoff exactly
    summary_df.loc[summary_df["profile_id"] == 2, "end_time"] = CUTOFF
    cls = split.classify_profiles(summary_df, CUTOFF)
    assert cls.loc[cls["profile_id"] == 2, "label"].iloc[0] == "excluded"


# --------------------------------------------------------------------------
# Spanning profile excluded (Req 8.3)
# --------------------------------------------------------------------------
def test_spanning_profile_excluded():
    # start before cutoff, end after cutoff
    start = CUTOFF - timedelta(minutes=30)
    summary_df, _ = _frames([(0, start, 3)])
    summary_df.loc[0, "end_time"] = CUTOFF + timedelta(minutes=30)
    cls = split.classify_profiles(summary_df, CUTOFF)
    assert cls.loc[0, "label"] == "excluded"


# --------------------------------------------------------------------------
# Whole-profile separation (Req 8.4)
# --------------------------------------------------------------------------
def test_whole_profile_separation(tmp_path):
    summary_df, points_df = _frames(
        [(0, BEFORE, 4), (1, AFTER, 5)]
    )
    out = _run_full(tmp_path, summary_df, points_df)
    train = pd.read_csv(os.path.join(out, "train_points.csv"))
    held = pd.read_csv(os.path.join(out, "heldout_points.csv"))
    train_ids = set(train["profile_id"])
    held_ids = set(held["profile_id"])
    # No profile appears in both points files.
    assert train_ids.isdisjoint(held_ids)
    # Every point lands in exactly one set (counts add up to the input).
    assert len(train) + len(held) == len(points_df)


# --------------------------------------------------------------------------
# ID-based leakage membership (Req 8.6) -- required
# --------------------------------------------------------------------------
def test_id_based_membership(tmp_path):
    summary_df, points_df = _frames([(0, BEFORE, 4), (1, AFTER, 4)])
    classification = split.classify_profiles(summary_df, CUTOFF)
    train_ids = set(
        classification.loc[classification["label"] == "train", "profile_id"]
    )
    held_ids = set(
        classification.loc[classification["label"] == "heldout", "profile_id"]
    )
    out = _run_full(tmp_path, summary_df, points_df)
    train = pd.read_csv(os.path.join(out, "train_points.csv"))
    held = pd.read_csv(os.path.join(out, "heldout_points.csv"))
    # Every row carries an id from its own set; the two sets are disjoint.
    assert set(train["profile_id"]) <= train_ids
    assert set(held["profile_id"]) <= held_ids
    assert train_ids.isdisjoint(held_ids)
    # Equal measured values across sets are fine -- temperatures match here and
    # that is explicitly NOT treated as leakage.
    assert 12.0 in set(train["temperature_c"]) and 12.0 in set(held["temperature_c"])


# --------------------------------------------------------------------------
# Candidate-sites structural columns (Req 8.5) -- required
# --------------------------------------------------------------------------
def test_candidate_sites_columns(tmp_path):
    summary_df, points_df = _frames([(0, BEFORE, 3), (1, AFTER, 3)])
    out = _run_full(tmp_path, summary_df, points_df)
    sites = pd.read_csv(os.path.join(out, "candidate_sites.csv"))
    assert list(sites.columns) == CANDIDATE_SITE_COLUMNS
    forbidden = {"end_time", "temperature_c", "depth_m", "temp_min", "temp_max",
                 "depth_min", "depth_max", "depth_range"}
    assert forbidden.isdisjoint(set(sites.columns))
    # Only the heldout profile is a candidate site.
    assert set(sites["profile_id"]) == {1}


# --------------------------------------------------------------------------
# CLI-driven malformed-input aborts (Req 6.2, 8.7, 8.8) -- run the real CLI
# against temporary Stage 1 CSVs and assert exit 1, a useful message, and no
# split artifacts written.
# --------------------------------------------------------------------------
def test_cli_duplicate_summary_aborts(tmp_path):
    # Same profile_id appears twice in the summary (Req 8.7).
    summary_df, points_df = _frames([(0, BEFORE, 3)])
    summary_df = pd.concat([summary_df, summary_df.iloc[[0]]], ignore_index=True)
    _assert_aborted_cli(
        tmp_path, summary_df, points_df,
        expected_in_message=["duplicate profile_id", "[0]"],
    )


def test_cli_time_mismatch_aborts(tmp_path):
    # Summary end_time no longer matches the latest point time (Req 8.8).
    summary_df, points_df = _frames([(0, BEFORE, 3)])
    summary_df.loc[0, "end_time"] = summary_df.loc[0, "end_time"] + timedelta(hours=5)
    _assert_aborted_cli(
        tmp_path, summary_df, points_df,
        expected_in_message=["summary start_time/end_time does not match", "[0]"],
    )


def test_cli_id_set_mismatch_aborts(tmp_path):
    # A summary profile_id with no matching points rows (Req 6.2).
    summary_df, points_df = _frames([(0, BEFORE, 3)])
    extra = summary_df.iloc[[0]].copy()
    extra["profile_id"] = 99
    summary_df = pd.concat([summary_df, extra], ignore_index=True)
    _assert_aborted_cli(
        tmp_path, summary_df, points_df,
        expected_in_message=["profile_id mismatch", "only_in_summary=[99]"],
    )


# --------------------------------------------------------------------------
# Empty-set handling: header-only CSV + null time ranges in the report
# --------------------------------------------------------------------------
def test_empty_set_handling(tmp_path):
    # Only a training profile -> heldout set is empty.
    summary_df, points_df = _frames([(0, BEFORE, 3)])
    out = _run_full(tmp_path, summary_df, points_df)
    held = pd.read_csv(os.path.join(out, "heldout_points.csv"))
    assert len(held) == 0
    assert list(held.columns) == split.POINT_COLUMNS
    with open(os.path.join(out, "split_report.json"), encoding="utf-8") as fh:
        report = json.load(fh)
    assert report["heldout"]["profile_count"] == 0
    assert report["heldout"]["time_range"] == {"start_min": None, "end_max": None}


# --------------------------------------------------------------------------
# A well-formed split writes all four artifacts
# --------------------------------------------------------------------------
def test_full_run_writes_all_artifacts(tmp_path):
    summary_df, points_df = _frames([(0, BEFORE, 4), (1, AFTER, 4)])
    out = _run_full(tmp_path, summary_df, points_df)
    for name in ARTIFACTS:
        assert os.path.exists(os.path.join(out, name))
