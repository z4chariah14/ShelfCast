"""Focused grouping and retention tests for Stage 1 build_profiles."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import pipeline

BASE = datetime(2024, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
GAP = timedelta(minutes=5)


def _readings(times, depths, lat=42.0, lon=-70.0):
    """Build a cleaned regional frame (typed time + numeric columns)."""
    rows = []
    for t, d in zip(times, depths):
        rows.append(
            {
                "time": t,
                "latitude": lat,
                "longitude": lon,
                "depth_m": d,
                "temperature_c": 12.0,
            }
        )
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def _even_depths(n, span=20.0):
    """n depths spread across `span` metres (range == span)."""
    if n == 1:
        return [0.0]
    step = span / (n - 1)
    return [round(i * step, 4) for i in range(n)]


def test_gap_split_separates_groups():
    # 12 readings, then a 30-min gap, then 12 more -- two groups, same location.
    times = [BASE + timedelta(seconds=30 * i) for i in range(12)]
    times += [t + timedelta(minutes=30) for t in times]
    depths = _even_depths(12) + _even_depths(12)
    df = _readings(times, depths)
    points, summary = pipeline.build_profiles(df, GAP)
    assert len(summary) == 2
    assert set(points["profile_id"]) == {0, 1}


def test_one_hour_span_split_retains_earlier_portion():
    # Small gaps (1 min) but total span exceeds 1 hour, so the run must be
    # split. Both resulting portions are large enough to be retained.
    n = 90
    times = [BASE + timedelta(minutes=i) for i in range(n)]
    depths = [0.0 if i % 2 == 0 else 20.0 for i in range(n)]
    df = _readings(times, depths)
    points, summary = pipeline.build_profiles(df, timedelta(minutes=5))
    # The span split yields at least two retained groups.
    assert len(summary) >= 2
    # Every retained profile spans at most 1 hour.
    for row in summary:
        start = datetime.fromisoformat(row["start_time"])
        end = datetime.fromisoformat(row["end_time"])
        assert (end - start) <= timedelta(hours=1)
    # The earliest group starts at the first reading (earlier portion kept)...
    ordered = sorted(summary, key=lambda r: r["start_time"])
    assert datetime.fromisoformat(ordered[0]["start_time"]) == BASE
    # ...and the next group starts exactly at the split point (no reading lost).
    first_end = datetime.fromisoformat(ordered[0]["end_time"])
    second_start = datetime.fromisoformat(ordered[1]["start_time"])
    assert second_start == first_end + timedelta(minutes=1)

def test_retention_exactly_min_readings_retained():
    n = pipeline.MIN_READINGS  # 10
    times = [BASE + timedelta(seconds=30 * i) for i in range(n)]
    depths = _even_depths(n, span=20.0)
    df = _readings(times, depths)
    points, summary = pipeline.build_profiles(df, GAP)
    assert len(summary) == 1
    assert summary[0]["n_readings"] == n


def test_retention_one_fewer_than_min_discarded():
    n = pipeline.MIN_READINGS - 1  # 9
    times = [BASE + timedelta(seconds=30 * i) for i in range(n)]
    depths = _even_depths(n, span=20.0)
    df = _readings(times, depths)
    points, summary = pipeline.build_profiles(df, GAP)
    assert len(summary) == 0


def test_retention_depth_range_exactly_min_retained():
    n = 12
    times = [BASE + timedelta(seconds=30 * i) for i in range(n)]
    depths = _even_depths(n, span=float(pipeline.MIN_DEPTH_RANGE_M))  # range == 10
    df = _readings(times, depths)
    points, summary = pipeline.build_profiles(df, GAP)
    assert len(summary) == 1
    assert abs(summary[0]["depth_range"] - pipeline.MIN_DEPTH_RANGE_M) < 1e-9


def test_retention_depth_range_just_under_min_discarded():
    n = 12
    times = [BASE + timedelta(seconds=30 * i) for i in range(n)]
    depths = _even_depths(n, span=float(pipeline.MIN_DEPTH_RANGE_M) - 0.5)  # 9.5
    df = _readings(times, depths)
    points, summary = pipeline.build_profiles(df, GAP)
    assert len(summary) == 0
