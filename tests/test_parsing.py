"""Focused parsing and validation tests for Stage 1 clean_readings."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import pipeline


def _raw(rows):
    """Build a raw (all-string) frame like load_archive returns."""
    return pd.DataFrame(rows, columns=pipeline.REQUIRED_COLUMNS, dtype=str)


def _one_valid(**over):
    row = {
        "time": "2024-08-01T12:00:00Z",
        "latitude": "42.0",
        "longitude": "-70.0",
        "depth_m": "15.0",
        "temperature_c": "12.5",
    }
    row.update(over)
    return row


def test_iso8601_z_timestamp_parses_to_utc():
    df = _raw([_one_valid()])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 1
    ts = cleaned["time"].iloc[0]
    assert ts.year == 2024 and ts.hour == 12
    assert str(ts.tz) == "UTC"
    assert counts["rejected_count"] == 0


def test_malformed_timestamp_rejected():
    df = _raw([_one_valid(time="not-a-time")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_non_numeric_value_rejected():
    df = _raw([_one_valid(depth_m="deep")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_temperature_unusual_but_finite_retained():
    df = _raw([_one_valid(temperature_c="999.0")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 1
    assert counts["rejected_count"] == 0


def test_temperature_missing_rejected():
    df = _raw([_one_valid(temperature_c="")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_temperature_non_finite_rejected():
    df = _raw([_one_valid(temperature_c="inf")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_invalid_latitude_rejected():
    df = _raw([_one_valid(latitude="100.0")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_invalid_longitude_rejected():
    df = _raw([_one_valid(longitude="-200.0")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_negative_depth_rejected():
    df = _raw([_one_valid(depth_m="-5.0")])
    cleaned, counts = pipeline.clean_readings(df)
    assert len(cleaned) == 0
    assert counts["rejected_count"] == 1


def test_exact_raw_duplicate_collapses():
    df = _raw([_one_valid(), _one_valid(), _one_valid(latitude="41.9")])
    cleaned, counts = pipeline.clean_readings(df)
    assert counts["input_count"] == 3
    assert counts["duplicate_count"] == 1
    assert len(cleaned) == 2


def test_duplicate_with_preserved_missing_text():
    # Two rows whose temperature cell is empty text must be treated as
    # identical raw rows and dedupe to one (missing-value text preserved).
    df = _raw([_one_valid(temperature_c=""), _one_valid(temperature_c="")])
    cleaned, counts = pipeline.clean_readings(df)
    assert counts["input_count"] == 2
    assert counts["duplicate_count"] == 1
    # The surviving row still has missing temperature, so it is rejected.
    assert counts["rejected_count"] == 1
    assert len(cleaned) == 0
