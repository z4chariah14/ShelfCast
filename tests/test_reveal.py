"""Required essential tests for the ShelfCast Stage 5 reveal loop.

Example-based pytest (no Hypothesis required). Covers the five essential MVP
guarantees: the reveal gate (heldout opened only after the click, and only by
read_revealed_profile), the profile filter (only the selected id's rows), model
preservation (temporary fit never writes; Results/model.joblib unchanged), depth
preservation (actuals keep their true recorded depths), and reset (selection
change / Reset replay clears the revealed state). Follows test_viewer.py
conventions: an open_spy fixture and a _require_model skip.

Groups are provisional candidate profiles inferred from recorded position and
time proximity -- never verified fishing tows or casts.
"""

import hashlib
import math
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import model, reveal, viewer
from shelfcast.config import (
    CANDIDATE_SITES_PATH,
    HELDOUT_POINTS_PATH,
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


def _require_model():
    if not os.path.exists(os.path.join(PROJECT_ROOT, MODEL_PATH)):
        pytest.skip("Results/model.joblib not present; run Scripts/train_model.py")


def _opened_heldout(opened):
    return [p for p in opened if "heldout_points.csv" in p]


def _first_heldout_id() -> int:
    frame = pd.read_csv(HELDOUT_POINTS_PATH, usecols=["profile_id"])
    return int(frame["profile_id"].iloc[0])


# --------------------------------------------------------------------------
# Required test 1 -- reveal gate (Property 6): pre-reveal paths never open the
# heldout file; it is opened only after the reveal call, and only by
# read_revealed_profile. (Req 2.3, 3.3, 3.5, 3.6, 3.7)
# --------------------------------------------------------------------------
def test_reveal_gate_pre_reveal_never_opens_heldout(open_spy):
    _require_model()
    # Exercise every pre-reveal path: load, map locations, sites, selection,
    # pre-reveal prediction, and the reset guard.
    viewer.load_metadata()
    fitted = viewer.load_fitted_model()
    viewer.load_training_locations()
    sites = viewer.load_candidate_sites()
    first_id = int(sites["profile_id"].iloc[0])
    site = model.lookup_candidate_site(first_id, CANDIDATE_SITES_PATH)
    viewer.predict_site_table(fitted, site, [5.0, 10.0, 20.0])
    session = {"revealed_profile_id": None, "revealed_df": None, "temp_model": None}
    reveal.reset_reveal_state(session, first_id)

    for path in open_spy.opened:
        for forbidden in FORBIDDEN_FILES:
            assert forbidden not in path, f"pre-reveal path opened {path}"


def test_reveal_gate_opens_heldout_only_on_reveal(open_spy):
    pid = _first_heldout_id()
    # Clear the spy record of the id-lookup read above, then do the reveal.
    open_spy.opened.clear()
    revealed = reveal.read_revealed_profile(pid)
    assert len(revealed) > 0
    assert _opened_heldout(open_spy.opened), "reveal did not open the heldout file"


# --------------------------------------------------------------------------
# Required test 2 -- profile filter (Property 1): only the selected id's rows
# are returned. (Req 3.1, 3.2)
# --------------------------------------------------------------------------
def test_profile_filter_returns_only_selected_id(tmp_path):
    frame = pd.DataFrame(
        {
            "time": ["2024-08-06T00:00:00+00:00"] * 4,
            "latitude": [41.9, 41.9, 42.0, 42.0],
            "longitude": [-69.8, -69.8, -69.9, -69.9],
            "depth_m": [10.0, 20.0, 15.0, 25.0],
            "temperature_c": [8.0, 7.5, 9.0, 8.5],
            "profile_id": [4, 4, 5, 5],
        }
    )
    path = tmp_path / "heldout_points.csv"
    frame.to_csv(path, index=False)

    out = reveal.read_revealed_profile(4, str(path))
    assert set(out["profile_id"].unique()) == {4}
    assert len(out) == 2
    assert list(out.columns) == reveal.REVEALED_COLUMNS


def test_missing_heldout_file_raises_file_not_found(tmp_path):
    # A missing heldout file surfaces FileNotFoundError so the app can report it
    # gracefully instead of crashing (Req 3.8).
    missing = tmp_path / "does_not_exist" / "heldout_points.csv"
    with pytest.raises(FileNotFoundError):
        reveal.read_revealed_profile(4, str(missing))


def test_profile_filter_missing_id_raises_naming_error(tmp_path):
    frame = pd.DataFrame(
        {
            "time": ["2024-08-06T00:00:00+00:00"],
            "latitude": [41.9],
            "longitude": [-69.8],
            "depth_m": [10.0],
            "temperature_c": [8.0],
            "profile_id": [4],
        }
    )
    path = tmp_path / "heldout_points.csv"
    frame.to_csv(path, index=False)

    with pytest.raises(KeyError, match="999"):
        reveal.read_revealed_profile(999, str(path))


# --------------------------------------------------------------------------
# Required test 3 -- model preservation (Property 4): the temporary fit writes
# nothing and the saved model bytes are unchanged. (Req 5.1, 5.3, 5.4)
# --------------------------------------------------------------------------
def test_model_preservation_temporary_fit_writes_nothing(monkeypatch):
    _require_model()
    model_abs = os.path.join(PROJECT_ROOT, MODEL_PATH)
    before = hashlib.sha256(open(model_abs, "rb").read()).hexdigest()

    # Any write via joblib.dump or a writable open must fail the test.
    import joblib

    def _no_dump(*a, **k):
        raise AssertionError("fit_temporary_model must not call joblib.dump")

    monkeypatch.setattr(joblib, "dump", _no_dump)

    train = reveal.load_training_rows(TRAIN_POINTS_PATH)
    revealed = reveal.read_revealed_profile(_first_heldout_id())
    temp = reveal.fit_temporary_model(train, revealed)
    assert temp is not None

    after = hashlib.sha256(open(model_abs, "rb").read()).hexdigest()
    assert before == after, "Results/model.joblib changed after a temporary fit"


# --------------------------------------------------------------------------
# Required test 4 -- depth preservation (Property 5): revealed depths are kept
# exactly, never snapped to the standard grid. (Req 4.1, 4.3)
# --------------------------------------------------------------------------
def test_depth_preservation_actuals_keep_true_depths():
    revealed = reveal.read_revealed_profile(_first_heldout_id())
    raw = pd.read_csv(HELDOUT_POINTS_PATH)
    expected = raw[raw["profile_id"] == _first_heldout_id()]["depth_m"].tolist()
    assert revealed["depth_m"].tolist() == [float(d) for d in expected]
    # None of the overlay depths were coerced onto the standard grid.
    standard = {5.0, 10.0, 20.0, 30.0, 50.0}
    assert any(float(d) not in standard for d in revealed["depth_m"])


# --------------------------------------------------------------------------
# Required test 5 -- reset (Property 8): selection change or Reset replay clears
# the revealed state and returns to the original model. (Req 7.1, 7.3, 7.5)
# --------------------------------------------------------------------------
def test_reset_on_profile_change_clears_state():
    session = {
        "revealed_profile_id": 4,
        "revealed_df": pd.DataFrame({"profile_id": [4]}),
        "temp_model": object(),
    }
    # Selecting a different profile must discard the stale reveal.
    reveal.reset_reveal_state(session, 5)
    assert session["revealed_profile_id"] is None
    assert session["revealed_df"] is None
    assert session["temp_model"] is None


def test_reset_replay_forces_full_clear():
    session = {
        "revealed_profile_id": 4,
        "revealed_df": pd.DataFrame({"profile_id": [4]}),
        "temp_model": object(),
    }
    # The explicit "Reset replay" path passes None to force a full clear.
    reveal.reset_reveal_state(session, None)
    assert all(session[k] is None for k in reveal.REVEAL_STATE_KEYS)


def test_reset_keeps_state_for_same_profile():
    marker = object()
    session = {
        "revealed_profile_id": 4,
        "revealed_df": pd.DataFrame({"profile_id": [4]}),
        "temp_model": marker,
    }
    reveal.reset_reveal_state(session, 4)
    assert session["revealed_profile_id"] == 4
    assert session["temp_model"] is marker


# --------------------------------------------------------------------------
# Nearest-site eligibility rule (required): the nearby comparison must be the
# geographically nearest candidate that is at least MIN_NEARBY_KM (1 km) away
# AND starts after the revealed profile's final recorded measurement. Distance
# is in kilometres; "no eligible nearby site" -> None. (Req 6.1, 6.6)
# --------------------------------------------------------------------------
# A simple fixture: the selected site 4, a too-close site 5 (~a few metres), a
# far-enough site 6 (~1.6 km north), and a far-enough-but-too-early site 7.
_FINAL = "2024-08-06T10:00:00+00:00"  # revealed profile's last measurement


def _sites():
    return pd.DataFrame(
        {
            "profile_id": [4, 5, 6, 7],
            "latitude": [41.9000, 41.9001, 41.9145, 41.9145],
            "longitude": [-69.8000, -69.8000, -69.8000, -69.8000],
            "start_time": [
                "2024-08-06T09:00:00+00:00",  # 4 selected (start irrelevant)
                "2024-08-06T11:00:00+00:00",  # 5 after, but < 1 km away
                "2024-08-06T11:00:00+00:00",  # 6 after and >= 1 km away (eligible)
                "2024-08-06T09:30:00+00:00",  # 7 >= 1 km away but starts too early
            ],
        }
    )


def test_haversine_km_distances():
    sites = _sites()
    # Site 5 is well under 1 km from site 4; site 6 is above 1 km.
    d5 = reveal.haversine_km(41.9000, -69.8000, 41.9001, -69.8000)
    d6 = reveal.haversine_km(41.9000, -69.8000, 41.9145, -69.8000)
    assert d5 < reveal.MIN_NEARBY_KM
    assert d6 >= reveal.MIN_NEARBY_KM
    assert sites is not None


def test_nearest_candidate_site_applies_km_and_after_time_rule():
    sites = _sites()
    # 5 is too close, 7 starts too early; only 6 is eligible.
    assert reveal.nearest_candidate_site(4, sites, _FINAL) == 6


def test_nearest_candidate_site_nearest_among_eligible_breaks_ties():
    # Two eligible, equidistant candidates -> lowest profile_id wins.
    sites = pd.DataFrame(
        {
            "profile_id": [4, 8, 9],
            "latitude": [41.9000, 41.9145, 41.9145],
            "longitude": [-69.8000, -69.8000, -69.8000],
            "start_time": [
                "2024-08-06T09:00:00+00:00",
                "2024-08-06T11:00:00+00:00",
                "2024-08-06T11:00:00+00:00",
            ],
        }
    )
    assert reveal.nearest_candidate_site(4, sites, _FINAL) == 8


def test_nearest_candidate_site_none_when_no_eligible():
    # Only a too-close site and a too-early site -> no eligible nearby site.
    sites = pd.DataFrame(
        {
            "profile_id": [4, 5, 7],
            "latitude": [41.9000, 41.9001, 41.9145],
            "longitude": [-69.8000, -69.8000, -69.8000],
            "start_time": [
                "2024-08-06T09:00:00+00:00",
                "2024-08-06T11:00:00+00:00",  # too close
                "2024-08-06T09:30:00+00:00",  # starts before final measurement
            ],
        }
    )
    assert reveal.nearest_candidate_site(4, sites, _FINAL) is None


def test_nearest_candidate_site_none_when_alone():
    sites = pd.DataFrame(
        {
            "profile_id": [4],
            "latitude": [41.9],
            "longitude": [-69.8],
            "start_time": ["2024-08-06T00:00:00+00:00"],
        }
    )
    assert reveal.nearest_candidate_site(4, sites, _FINAL) is None


def test_revealed_final_time_is_max_recorded_time():
    revealed = pd.DataFrame(
        {
            "time": [
                "2024-08-06T10:38:31+00:00",
                "2024-08-06T10:40:02+00:00",
                "2024-08-06T10:39:15+00:00",
            ],
            "depth_m": [10.0, 20.0, 15.0],
            "temperature_c": [8.0, 7.5, 7.8],
            "latitude": [41.96] * 3,
            "longitude": [-69.82] * 3,
            "profile_id": [4] * 3,
        }
    )
    final = reveal.revealed_final_time(revealed)
    assert str(final) == "2024-08-06 10:40:02+00:00"


def test_nearby_site_delta_is_prediction_difference():
    _require_model()
    original = viewer.load_fitted_model()
    train = reveal.load_training_rows(TRAIN_POINTS_PATH)
    revealed = reveal.read_revealed_profile(_first_heldout_id())
    temp = reveal.fit_temporary_model(train, revealed)
    site = model.lookup_candidate_site(
        _first_heldout_id(), CANDIDATE_SITES_PATH
    )
    out = reveal.nearby_site_delta(original, temp, site, depth=20.0)
    assert math.isclose(out["delta"], out["updated"] - out["original"], rel_tol=1e-9)
    assert out["depth"] == 20.0
