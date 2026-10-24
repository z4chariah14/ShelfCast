"""Required essential tests for the ShelfCast Stage 6 spread + suggestion engine.

Example-based pytest (no Hypothesis required). Covers the essential MVP
guarantees for shelfcast/spread.py:

- profile-level resampling (whole profiles only, never individual readings),
- reproducibility of the five fixed-seed models and a < 2-profile guard,
- candidate eligibility and tie-breaking for the suggestion,
- reveal/reset isolation (updated spread models are reveal-scoped and include
  exactly the training rows plus the one revealed profile),
- the hidden-data boundary (pre-reveal spread + suggestion never open the
  heldout file; the fit writes nothing and leaves Results/model.joblib intact).

Follows tests/test_reveal.py conventions: an open_spy fixture and a
_require_model skip.

Groups are provisional candidate profiles inferred from recorded position and
time proximity -- never verified fishing tows or casts.
"""

import hashlib
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shelfcast import model, reveal, spread
from shelfcast.config import (
    CANDIDATE_SITES_PATH,
    HELDOUT_POINTS_PATH,
    MODEL_PATH,
    SPREAD_SEEDS,
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


def _first_heldout_id() -> int:
    frame = pd.read_csv(HELDOUT_POINTS_PATH, usecols=["profile_id"])
    return int(frame["profile_id"].iloc[0])


def _toy_train() -> pd.DataFrame:
    """Three distinct candidate profiles with differing row counts."""
    rows = []
    specs = {
        0: (41.80, -70.30, 4),
        1: (41.90, -70.10, 3),
        2: (42.00, -69.90, 5),
    }
    for pid, (lat, lon, n) in specs.items():
        for i in range(n):
            rows.append(
                {
                    "time": f"2024-08-0{1 + (i % 5)}T10:0{i}:00+00:00",
                    "latitude": lat,
                    "longitude": lon,
                    "depth_m": 5.0 + 3.0 * i,
                    "temperature_c": 8.0 + 0.1 * i + 0.2 * pid,
                    "profile_id": pid,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Required test 1 -- profile-level resampling (Property 1): whole profiles only,
# never individual readings. (Req 1.1, 1.2)
# --------------------------------------------------------------------------
def test_resample_keeps_whole_profiles():
    train = _toy_train()
    counts = train.groupby("profile_id").size().to_dict()
    for seed in SPREAD_SEEDS:
        sample = spread.resample_profiles(train, seed)
        # Every present profile contributes a whole-number multiple of its own
        # full row count -- i.e. only whole profiles, never partial ones.
        present = sample["profile_id"].unique()
        for pid in present:
            n = int((sample["profile_id"] == pid).sum())
            assert n % counts[pid] == 0 and n >= counts[pid]
        # A profile-level bootstrap draws len(ids) whole profiles with
        # replacement, so the total row count is the sum of the full row count
        # of each drawn id (each appearing n // counts[pid] times).
        expected_rows = sum(
            counts[pid] * (int((sample["profile_id"] == pid).sum()) // counts[pid])
            for pid in present
        )
        assert len(sample) == expected_rows
        # Exactly len(ids) whole-profile draws were made.
        total_draws = sum(
            int((sample["profile_id"] == pid).sum()) // counts[pid] for pid in present
        )
        assert total_draws == len(counts)


def test_resample_is_deterministic_for_seed():
    train = _toy_train()
    a = spread.resample_profiles(train, 101)
    b = spread.resample_profiles(train, 101)
    assert a.reset_index(drop=True).equals(b.reset_index(drop=True))


def test_resample_requires_two_profiles():
    train = _toy_train()
    one = train[train["profile_id"] == 0]
    with pytest.raises(ValueError, match="at least 2"):
        spread.resample_profiles(one, 101)


# --------------------------------------------------------------------------
# Required test 2 -- reproducibility (Property 2) + < 2-profile guard.
# (Req 1.3, 1.5, 3.4)
# --------------------------------------------------------------------------
def test_fit_spread_models_reproducible():
    train = _toy_train()
    models_a = spread.fit_spread_models(train)
    models_b = spread.fit_spread_models(train)
    assert len(models_a) == len(SPREAD_SEEDS) == 5

    site = {
        "latitude": 41.95,
        "longitude": -70.0,
        "start_time": "2024-08-06T10:00:00+00:00",
    }
    ta = spread.spread_table(models_a, site)
    tb = spread.spread_table(models_b, site)
    assert ta.equals(tb)

    sa = spread.disagreement_score(models_a, 41.95, -70.0, "2024-08-06T10:00:00+00:00")
    sb = spread.disagreement_score(models_b, 41.95, -70.0, "2024-08-06T10:00:00+00:00")
    assert sa == sb
    assert sa >= 0.0


def test_fit_spread_models_requires_two_profiles():
    one = _toy_train()
    one = one[one["profile_id"] == 1]
    with pytest.raises(ValueError, match="at least 2"):
        spread.fit_spread_models(one)


# --------------------------------------------------------------------------
# Required test 3 -- candidate eligibility + tie-breaking (Property 3).
# (Req 4.1, 4.2, 4.3, 5.1, 5.4)
# --------------------------------------------------------------------------
# selected site 4 at (41.9000, -69.8000); site 5 ~a few metres away (too close);
# site 6 ~1.6 km north (eligible); site 7 far enough but starts too early.
_SELECTED = {
    "latitude": 41.9000,
    "longitude": -69.8000,
    "start_time": "2024-08-06T09:00:00+00:00",
}


def _sites():
    return pd.DataFrame(
        {
            "profile_id": [4, 5, 6, 7],
            "latitude": [41.9000, 41.9001, 41.9145, 41.9145],
            "longitude": [-69.8000, -69.8000, -69.8000, -69.8000],
            "start_time": [
                "2024-08-06T09:00:00+00:00",  # 4 selected
                "2024-08-06T11:00:00+00:00",  # 5 after, but < 1 km away
                "2024-08-06T11:00:00+00:00",  # 6 after and >= 1 km (eligible)
                "2024-08-06T08:00:00+00:00",  # 7 >= 1 km but starts too early
            ],
        }
    )


def test_eligible_candidates_applies_km_and_after_time():
    sites = _sites()
    after = _SELECTED["start_time"]
    assert spread.eligible_candidates(sites, 4, _SELECTED, after) == [6]


class _ConstModel:
    """A fake model whose prediction depends only on latitude, giving a
    controllable, deterministic disagreement score per site."""

    def __init__(self, bias: float):
        self.bias = bias

    def predict(self, rows):
        # rows are [lat, lon, depth, hours]; return lat-scaled + bias.
        return [float(r[0]) * 10.0 + self.bias for r in rows]


class _LatScaledModel:
    """A fake model whose per-model bias is scaled by the site's longitude, so
    the five-model disagreement (max - min across models) at a site grows with
    |longitude - LON0|. This lets a test give two eligible candidates genuinely
    DIFFERENT disagreement scores and check the higher one is chosen."""

    LON0 = -69.8000

    def __init__(self, bias: float):
        self.bias = bias

    def predict(self, rows):
        # rows are [lat, lon, depth, hours]. Spread across models at a site is
        # bias * |lon - LON0|, which differs between sites at different lon.
        return [self.bias * abs(float(r[1]) - self.LON0) for r in rows]


def test_suggest_candidate_prefers_genuinely_higher_score():
    # Two eligible candidates, both >= 1 km away and starting after the cutoff,
    # at DIFFERENT longitudes so their disagreement scores genuinely differ.
    # The higher-score candidate (farther in longitude from LON0) must win even
    # though it has the HIGHER profile_id -- so the choice is driven by score,
    # not by the lowest-id tie-break.
    sites = pd.DataFrame(
        {
            "profile_id": [4, 8, 20],
            "latitude": [41.9000, 41.9145, 41.9145],
            # id 8 is near LON0 (small spread); id 20 is far (large spread).
            "longitude": [-69.8000, -69.8050, -69.9000],
            "start_time": [
                "2024-08-06T09:00:00+00:00",
                "2024-08-06T11:00:00+00:00",
                "2024-08-06T11:00:00+00:00",
            ],
        }
    )
    models = [_LatScaledModel(0.0), _LatScaledModel(50.0)]
    score_8 = spread.disagreement_score(
        models, 41.9145, -69.8050, "2024-08-06T11:00:00+00:00"
    )
    score_20 = spread.disagreement_score(
        models, 41.9145, -69.9000, "2024-08-06T11:00:00+00:00"
    )
    # Precondition: the two candidates really do have different scores and the
    # higher score belongs to the higher-id candidate.
    assert score_20 > score_8 > 0.0

    out = spread.suggest_candidate(models, sites, 4, _SELECTED, _SELECTED["start_time"])
    assert out is not None
    assert out["profile_id"] == 20  # higher score wins over lower id
    assert out["score"] == pytest.approx(score_20)


def test_suggest_candidate_picks_highest_score_then_lowest_id():
    # Two eligible, equidistant candidates at the same latitude so their
    # disagreement scores tie -> lowest profile_id must win.
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
    models = [_ConstModel(0.0), _ConstModel(1.0), _ConstModel(2.5)]
    out = spread.suggest_candidate(models, sites, 4, _SELECTED, _SELECTED["start_time"])
    assert out is not None
    assert out["profile_id"] == 8  # tie on score -> lowest id
    assert out["score"] >= 0.0


def test_suggest_candidate_none_when_no_eligible():
    sites = pd.DataFrame(
        {
            "profile_id": [4, 5, 7],
            "latitude": [41.9000, 41.9001, 41.9145],
            "longitude": [-69.8000, -69.8000, -69.8000],
            "start_time": [
                "2024-08-06T09:00:00+00:00",
                "2024-08-06T11:00:00+00:00",  # too close
                "2024-08-06T08:00:00+00:00",  # starts too early
            ],
        }
    )
    models = [_ConstModel(0.0), _ConstModel(1.0)]
    assert (
        spread.suggest_candidate(models, sites, 4, _SELECTED, _SELECTED["start_time"])
        is None
    )


# --------------------------------------------------------------------------
# Required test 4 -- reveal/reset isolation (Property 6 + reset). The updated
# spread models are reveal-scoped; the fit includes exactly the training rows
# plus the one revealed profile. (Req 6.1, 6.4, 7.1, 7.2)
# --------------------------------------------------------------------------
def test_reset_replay_clears_updated_spread_models():
    assert "spread_models_updated" in reveal.REVEAL_STATE_KEYS
    session = {
        "revealed_profile_id": 4,
        "revealed_df": pd.DataFrame({"profile_id": [4]}),
        "temp_model": object(),
        "spread_models_updated": [object()],
    }
    # Selecting a different profile must discard the stale updated spread.
    reveal.reset_reveal_state(session, 5)
    assert session["spread_models_updated"] is None
    # Explicit Reset replay (None) also clears it.
    session["spread_models_updated"] = [object()]
    session["revealed_profile_id"] = 4
    reveal.reset_reveal_state(session, None)
    assert session["spread_models_updated"] is None


def test_updated_fit_includes_only_training_plus_revealed(monkeypatch):
    train = _toy_train()
    revealed = pd.DataFrame(
        {
            "time": ["2024-08-06T10:00:00+00:00", "2024-08-06T10:01:00+00:00"],
            "latitude": [41.96, 41.96],
            "longitude": [-69.82, -69.82],
            "depth_m": [12.0, 24.0],
            "temperature_c": [7.7, 7.2],
            "profile_id": [99, 99],
        }
    )
    captured = []

    real_fit = model.fit_model

    def spy_fit(df, *a, **k):
        captured.append(df.copy())
        return real_fit(df, *a, **k)

    monkeypatch.setattr(model, "fit_model", spy_fit)
    monkeypatch.setattr(spread.model, "fit_model", spy_fit)

    spread.fit_spread_models(train, revealed)
    assert len(captured) == 5

    cols = spread.FIT_SOURCE_COLUMNS
    revealed_src = revealed[cols].reset_index(drop=True)

    for seed, frame in zip(SPREAD_SEEDS, captured):
        # Independently reconstruct what this seed's resample must be: a
        # whole-profile bootstrap of the training rows (same seed, deterministic).
        expected_resample = spread.resample_profiles(train, seed)[cols]
        expected = pd.concat([expected_resample, revealed_src], ignore_index=True)

        got = frame[cols].reset_index(drop=True)
        # The fit frame must be EXACTLY the whole-profile training resample
        # followed by exactly the selected revealed rows -- no more, no less.
        pd.testing.assert_frame_equal(got, expected, check_like=False)

        # And the trailing rows are precisely the revealed rows, in order.
        tail = frame[cols].tail(len(revealed_src)).reset_index(drop=True)
        pd.testing.assert_frame_equal(tail, revealed_src)

        # The leading block is a whole-profile resample: every training row in it
        # belongs to a training profile and appears a whole-profile multiple of
        # times (no partial profile, no stray/other-profile rows).
        lead = frame[cols].head(len(frame) - len(revealed_src)).reset_index(drop=True)
        pd.testing.assert_frame_equal(lead, expected_resample.reset_index(drop=True))

    # The only profile ids that may contribute are the training ids plus the one
    # revealed id -- confirmed structurally by the exact-equality checks above.
    train_profiles = set(train["profile_id"].unique())
    assert 99 not in train_profiles  # the revealed profile is genuinely new


# --------------------------------------------------------------------------
# Required test 5 -- hidden-data boundary (Property 4/5). Pre-reveal spread +
# suggestion never open the heldout/summary files; the fit writes nothing and
# leaves Results/model.joblib unchanged. (Req 1.4, 1.6, 3.3, 5.5, 8.1, 8.2, 8.3)
# --------------------------------------------------------------------------
def test_spread_and_suggestion_never_open_hidden_files(open_spy):
    # Load the full training rows and candidate sites the way app.py will.
    train_df = pd.read_csv(TRAIN_POINTS_PATH)
    sites_df = pd.read_csv(
        CANDIDATE_SITES_PATH,
        usecols=["profile_id", "latitude", "longitude", "start_time"],
    )
    open_spy.opened.clear()

    models = spread.fit_spread_models(train_df)
    first_id = int(sites_df["profile_id"].iloc[0])
    selected_site = model.lookup_candidate_site(first_id, CANDIDATE_SITES_PATH)
    spread.spread_table(models, selected_site)
    spread.suggest_candidate(
        models, sites_df, first_id, selected_site, selected_site["start_time"]
    )

    for path in open_spy.opened:
        for forbidden in FORBIDDEN_FILES:
            assert forbidden not in path, f"spread/suggestion opened {path}"


def test_fit_spread_models_writes_nothing(monkeypatch):
    _require_model()
    model_abs = os.path.join(PROJECT_ROOT, MODEL_PATH)
    before = hashlib.sha256(open(model_abs, "rb").read()).hexdigest()

    import joblib

    def _no_dump(*a, **k):
        raise AssertionError("fit_spread_models must not call joblib.dump")

    monkeypatch.setattr(joblib, "dump", _no_dump)

    train_df = pd.read_csv(TRAIN_POINTS_PATH)
    models = spread.fit_spread_models(train_df)
    assert len(models) == 5

    after = hashlib.sha256(open(model_abs, "rb").read()).hexdigest()
    assert before == after, "Results/model.joblib changed after a spread fit"
