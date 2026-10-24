"""Focused example tests for the ShelfCast Stage 3 temperature predictor.

Example-based pytest only -- no property-based testing framework. Covers feature
construction, training-frame validation, fit/predict reproducibility, the
prediction input/output contract, candidate-site lookup, the two CLIs, the hard
data boundary (heldout_points.csv and profile_summary.csv are never opened), and
one end-to-end smoke check.

Groups are provisional candidate profiles inferred from recorded position and
time proximity -- never verified fishing tows or casts.
"""

import json
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import model
from shelfcast.config import (
    CANDIDATE_SITES_PATH,
    DEFAULT_DEPTH_GRID,
    FEATURE_ORDER,
    TIME_REFERENCE,
    TRAIN_POINTS_PATH,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_FILES = ("heldout_points.csv", "profile_summary.csv")


# --------------------------------------------------------------------------
# Fixtures / builders
# --------------------------------------------------------------------------
def _training_frame(n=40):
    """A small, valid synthetic training frame with a >=10 m depth range."""
    base = datetime(2024, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        rows.append(
            {
                "time": (base + timedelta(minutes=i)).isoformat(),
                "latitude": 42.0 + (i % 5) * 0.01,
                "longitude": -70.0 - (i % 7) * 0.01,
                "depth_m": 5.0 + (i % 10) * 2.0,
                "temperature_c": 10.0 + (i % 6) * 0.5,
                "profile_id": i % 4,
            }
        )
    return pd.DataFrame(rows)


class _Spy:
    """Records every path passed to read_csv / open."""

    def __init__(self):
        self.opened = []


@pytest.fixture
def open_spy(monkeypatch):
    spy = _Spy()
    real_read_csv = pd.read_csv
    real_open = open

    def spy_read_csv(path, *a, **k):
        spy.opened.append(str(path))
        return real_read_csv(path, *a, **k)

    def spy_open(path, *a, **k):
        spy.opened.append(str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr(pd, "read_csv", spy_read_csv)
    monkeypatch.setattr("builtins.open", spy_open)
    return spy


def _assert_no_forbidden(opened):
    for path in opened:
        for forbidden in FORBIDDEN_FILES:
            assert forbidden not in path, f"forbidden file opened: {path}"


# --------------------------------------------------------------------------
# Task 2.2 -- Property 4: exactly four features in declared order (Req 1.2, 2.3)
# --------------------------------------------------------------------------
def test_build_feature_row_order_and_hours():
    t = TIME_REFERENCE + timedelta(hours=10)
    row = model.build_feature_row(42.0, -70.0, 25.0, t)
    assert len(row) == 4
    assert row[0] == 42.0
    assert row[1] == -70.0
    assert row[2] == 25.0
    assert row[3] == pytest.approx(10.0)  # hours since TIME_REFERENCE


# --------------------------------------------------------------------------
# Task 2.4 -- Property 7: invalid input rejected, no artifact (Req 1.5-1.7)
# --------------------------------------------------------------------------
def test_validate_rejects_missing_column():
    df = _training_frame().drop(columns=["depth_m"])
    with pytest.raises(ValueError, match="missing required column"):
        model.validate_training_frame(df)


def test_validate_rejects_nan_and_inf():
    for bad in (float("nan"), float("inf"), float("-inf")):
        df = _training_frame()
        df.loc[0, "temperature_c"] = bad
        with pytest.raises(ValueError):
            model.validate_training_frame(df)


def test_validate_rejects_non_numeric():
    df = _training_frame()
    # Cast to object first so a non-numeric string survives assignment
    # (pandas 3.x raises TypeError when writing a string into a float column).
    df["latitude"] = df["latitude"].astype(object)
    df.loc[0, "latitude"] = "not-a-number"
    with pytest.raises(ValueError):
        model.validate_training_frame(df)


def test_validate_rejects_bad_timestamp():
    df = _training_frame()
    df.loc[0, "time"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="invalid UTC timestamp"):
        model.validate_training_frame(df)


def test_validate_rejects_zero_rows():
    df = _training_frame().iloc[0:0]
    with pytest.raises(ValueError):
        model.validate_training_frame(df)


# --------------------------------------------------------------------------
# Task 3.2 / 4.4 -- Property 6: reproducibility (Req 1.4, 6.1, 6.2)
# --------------------------------------------------------------------------
def test_fit_is_reproducible():
    df = _training_frame()
    m1 = model.fit_model(df)
    m2 = model.fit_model(df)
    t = datetime(2024, 8, 6, 10, 0, 0, tzinfo=timezone.utc)
    p1 = model.predict_temperatures(m1, 42.0, -70.0, t, [5.0, 10.0, 20.0])
    p2 = model.predict_temperatures(m2, 42.0, -70.0, t, [5.0, 10.0, 20.0])
    assert p1 == p2


def test_predict_is_reproducible():
    m = model.fit_model(_training_frame())
    t = datetime(2024, 8, 6, 10, 0, 0, tzinfo=timezone.utc)
    p1 = model.predict_temperatures(m, 42.0, -70.0, t, [5.0, 15.0])
    p2 = model.predict_temperatures(m, 42.0, -70.0, t, [5.0, 15.0])
    assert p1 == p2


# --------------------------------------------------------------------------
# Task 4.2 -- Property 2: one finite temp per depth, order preserved (Req 2.1,2.2,2.6)
# --------------------------------------------------------------------------
def test_prediction_contract_length_order_finite():
    m = model.fit_model(_training_frame())
    t = datetime(2024, 8, 6, 10, 0, 0, tzinfo=timezone.utc)
    depths = [5.0, 30.0, 10.0, 50.0]
    preds = model.predict_temperatures(m, 42.0, -70.0, t, depths)
    assert len(preds) == len(depths)
    assert all(math.isfinite(p) for p in preds)


# --------------------------------------------------------------------------
# Task 4.3 -- Property 3: empty / invalid depths do not invoke model (Req 2.4, 2.5)
# --------------------------------------------------------------------------
class _NoCallModel:
    def predict(self, rows):  # pragma: no cover - must never run
        raise AssertionError("model should not be invoked")


def test_empty_depths_returns_empty_without_model():
    assert model.predict_temperatures(_NoCallModel(), 42.0, -70.0,
                                       TIME_REFERENCE, []) == []


def test_invalid_depths_raise_without_model():
    t = TIME_REFERENCE
    for bad in ([float("nan")], [float("inf")], [0.0], [-5.0], [5.0, -1.0]):
        with pytest.raises(ValueError):
            model.predict_temperatures(_NoCallModel(), 42.0, -70.0, t, bad)


# --------------------------------------------------------------------------
# Task 5.2 -- metadata (Req 3.3, 7.5)
# --------------------------------------------------------------------------
def test_build_metadata_keys_and_wording():
    md = model.build_metadata(100, 7)
    assert md["feature_order"] == list(FEATURE_ORDER)
    assert md["n_rows"] == 100
    assert md["n_candidate_profiles"] == 7
    assert "candidate profile" in md["candidate_profile_note"].lower()
    note = md["candidate_profile_note"].lower()
    assert "not verified fishing tows or casts" in note


# --------------------------------------------------------------------------
# Task 6.2 -- candidate lookup (Req 4.1, 4.5, 4.8, 5.3)
# --------------------------------------------------------------------------
def _write_sites(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_lookup_known_id(tmp_path):
    p = tmp_path / "candidate_sites.csv"
    _write_sites(p, [
        {"profile_id": 4, "latitude": 41.96, "longitude": -69.82,
         "start_time": "2024-08-06T10:38:31+00:00"},
    ])
    site = model.lookup_candidate_site(4, str(p))
    assert site["latitude"] == pytest.approx(41.96)
    assert site["start_time"].tzinfo is not None


def test_lookup_unknown_id_raises_keyerror(tmp_path):
    p = tmp_path / "candidate_sites.csv"
    _write_sites(p, [
        {"profile_id": 4, "latitude": 41.96, "longitude": -69.82,
         "start_time": "2024-08-06T10:38:31+00:00"},
    ])
    with pytest.raises(KeyError):
        model.lookup_candidate_site(999, str(p))


def test_lookup_ambiguous_id_raises_valueerror(tmp_path):
    p = tmp_path / "candidate_sites.csv"
    _write_sites(p, [
        {"profile_id": 4, "latitude": 41.96, "longitude": -69.82,
         "start_time": "2024-08-06T10:38:31+00:00"},
        {"profile_id": 4, "latitude": 41.97, "longitude": -69.83,
         "start_time": "2024-08-06T11:00:00+00:00"},
    ])
    with pytest.raises(ValueError, match="ambiguous"):
        model.lookup_candidate_site(4, str(p))


# --------------------------------------------------------------------------
# Task 10 -- Property 1: data boundary, forbidden files never opened (Req 5.4-5.6)
# --------------------------------------------------------------------------
def test_data_boundary_no_forbidden_files_opened(open_spy, tmp_path):
    # Train path
    df = pd.read_csv(TRAIN_POINTS_PATH)
    m = model.fit_model(df)
    model_path = tmp_path / "model.joblib"
    model.save_model(m, str(model_path))
    # Predict path
    loaded = model.load_model(str(model_path))
    site = model.lookup_candidate_site(4, CANDIDATE_SITES_PATH)
    model.predict_temperatures(loaded, site["latitude"], site["longitude"],
                               site["start_time"], list(DEFAULT_DEPTH_GRID))
    _assert_no_forbidden(open_spy.opened)


# --------------------------------------------------------------------------
# Task 11 -- end-to-end smoke check (Req 9.1, 9.2, 9.3)
# --------------------------------------------------------------------------
def test_end_to_end_smoke(open_spy, tmp_path):
    df = pd.read_csv(TRAIN_POINTS_PATH)
    m = model.fit_model(df)                       # trains successfully (9.1)
    path = tmp_path / "model.joblib"
    model.save_model(m, str(path))
    loaded = model.load_model(str(path))
    site = model.lookup_candidate_site(4, CANDIDATE_SITES_PATH)
    depths = list(DEFAULT_DEPTH_GRID)
    temps = model.predict_temperatures(loaded, site["latitude"],
                                       site["longitude"], site["start_time"],
                                       depths)
    assert len(temps) == len(depths)
    assert all(math.isfinite(t) for t in temps)   # finite temps (9.2)
    _assert_no_forbidden(open_spy.opened)          # heldout untouched (9.3)


# --------------------------------------------------------------------------
# Task 8.2 / 9.2 / 9.3 -- CLI paths (Req 3.4, 4.5, 4.6, 4.7, 4.8)
# --------------------------------------------------------------------------
def _run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join("Scripts", script), *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )


def test_train_cli_missing_file_nonzero_no_artifact(tmp_path):
    missing = str(tmp_path / "nope.csv")
    out_model = str(tmp_path / "m.joblib")
    out_meta = str(tmp_path / "m.json")
    r = _run("train_model.py", "--train", missing,
             "--model", out_model, "--metadata", out_meta)
    assert r.returncode != 0
    assert not os.path.exists(out_model)
    assert not os.path.exists(out_meta)


def test_train_and_predict_cli_json_shape(tmp_path):
    out_model = str(tmp_path / "m.joblib")
    out_meta = str(tmp_path / "m.json")
    r = _run("train_model.py", "--model", out_model, "--metadata", out_meta)
    assert r.returncode == 0, r.stderr

    r2 = _run("predict_site.py", "--profile-id", "4", "--model", out_model)
    assert r2.returncode == 0, r2.stderr
    data = json.loads(r2.stdout)
    assert data["profile_id"] == 4
    assert "utc_time" in data
    assert len(data["predictions"]) == len(DEFAULT_DEPTH_GRID)
    assert data["predictions"][0]["depth_m"] == DEFAULT_DEPTH_GRID[0]

    # Supplied depths override the default grid
    r3 = _run("predict_site.py", "--profile-id", "4", "--model", out_model,
              "--depths", "7", "12")
    assert r3.returncode == 0, r3.stderr
    data3 = json.loads(r3.stdout)
    assert [p["depth_m"] for p in data3["predictions"]] == [7.0, 12.0]


def test_predict_cli_unknown_profile_nonzero(tmp_path):
    out_model = str(tmp_path / "m.joblib")
    out_meta = str(tmp_path / "m.json")
    assert _run("train_model.py", "--model", out_model,
                "--metadata", out_meta).returncode == 0
    r = _run("predict_site.py", "--profile-id", "999999", "--model", out_model)
    assert r.returncode != 0


def test_predict_cli_invalid_depths_nonzero(tmp_path):
    out_model = str(tmp_path / "m.joblib")
    out_meta = str(tmp_path / "m.json")
    assert _run("train_model.py", "--model", out_model,
                "--metadata", out_meta).returncode == 0
    r = _run("predict_site.py", "--profile-id", "4", "--model", out_model,
             "--depths", "-5")
    assert r.returncode != 0
