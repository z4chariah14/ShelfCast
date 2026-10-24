"""Focused example tests for the ShelfCast Stage 4 viewer helpers.

Example-based pytest only. Covers the hard data boundary (heldout_points.csv and
profile_summary.csv are never opened by the app's loaders or a site prediction),
CLI parity (the chart table equals the reused Stage 3 prediction path), the
per-depth output contract, and the usecols whitelists. Does not launch Streamlit
-- all testable logic lives in shelfcast/viewer.py.

Groups are provisional candidate profiles inferred from recorded position and
time proximity -- never verified fishing tows or casts.
"""

import math
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import model, viewer
from shelfcast.config import (
    CANDIDATE_SITES_PATH,
    DEFAULT_DEPTH_GRID,
    MODEL_PATH,
    TRAIN_POINTS_PATH,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_FILES = ("heldout_points.csv", "profile_summary.csv")


class _Spy:
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


def _require_model():
    if not os.path.exists(os.path.join(PROJECT_ROOT, MODEL_PATH)):
        pytest.skip("Results/model.joblib not present; run Scripts/train_model.py")


# --------------------------------------------------------------------------
# Property 1 -- data boundary: forbidden files never opened (Req 6.1, 6.2, 6.4)
# --------------------------------------------------------------------------
def test_viewer_data_boundary_no_forbidden_files(open_spy):
    _require_model()
    viewer.load_metadata()
    fitted = viewer.load_fitted_model()
    viewer.load_training_locations()
    sites = viewer.load_candidate_sites()
    first_id = int(sites["profile_id"].iloc[0])
    site = model.lookup_candidate_site(first_id, CANDIDATE_SITES_PATH)
    viewer.predict_site_table(fitted, site, list(DEFAULT_DEPTH_GRID))
    _assert_no_forbidden(open_spy.opened)


# --------------------------------------------------------------------------
# Property 2 -- CLI parity: chart table equals the reused prediction path (Req 4.1, 4.2, 7.2)
# --------------------------------------------------------------------------
def test_predict_site_table_matches_direct_prediction():
    _require_model()
    fitted = viewer.load_fitted_model()
    site = model.lookup_candidate_site(4, CANDIDATE_SITES_PATH)
    depths = list(DEFAULT_DEPTH_GRID)

    table = viewer.predict_site_table(fitted, site, depths)
    direct = model.predict_temperatures(
        fitted, site["latitude"], site["longitude"], site["start_time"], depths
    )
    assert table["temperature_c"].tolist() == [float(t) for t in direct]
    assert table["depth_m"].tolist() == [float(d) for d in depths]


# --------------------------------------------------------------------------
# Property 3 -- one row per standard depth, in order, all finite (Req 4.2)
# --------------------------------------------------------------------------
def test_predict_site_table_depth_contract():
    _require_model()
    fitted = viewer.load_fitted_model()
    site = model.lookup_candidate_site(4, CANDIDATE_SITES_PATH)
    depths = list(DEFAULT_DEPTH_GRID)

    table = viewer.predict_site_table(fitted, site, depths)
    assert list(table.columns) == ["depth_m", "temperature_c"]
    assert len(table) == len(depths)
    assert table["depth_m"].tolist() == [float(d) for d in depths]
    assert all(math.isfinite(t) for t in table["temperature_c"])


# --------------------------------------------------------------------------
# usecols whitelists -- only allowed columns are read (Req 6.2, 6.3)
# --------------------------------------------------------------------------
def test_training_locations_reads_only_lat_lon():
    df = viewer.load_training_locations()
    assert sorted(df.columns) == ["latitude", "longitude"]


def test_candidate_sites_reads_only_four_columns():
    df = viewer.load_candidate_sites()
    assert sorted(df.columns) == sorted(
        ["profile_id", "latitude", "longitude", "start_time"]
    )
