"""Preference trainer Phase A nudge."""

import pytest

from colayout.preference.trainer import PreferenceTrainer, PHASE_A_LIMIT
from colayout.preference.theta import default_theta


@pytest.fixture
def pref_tmp(tmp_path, monkeypatch):
    golden_dir = tmp_path / "golden_layouts"
    golden_dir.mkdir()
    comp = tmp_path / "preference" / "comparisons.jsonl"
    comp.parent.mkdir(parents=True)
    state = tmp_path / "preference" / "theta_state.json"
    monkeypatch.setattr("colayout.preference.store.GOLDEN_DIR", golden_dir)
    monkeypatch.setattr("colayout.preference.store.COMPARISONS_PATH", comp)
    monkeypatch.setattr("colayout.preference.store.THETA_STATE_PATH", state)
    return tmp_path


def test_trainer_nudge_on_compare(pref_tmp):
    trainer = PreferenceTrainer("bedroom")
    theta_a = default_theta("bedroom")
    theta_b = dict(theta_a)
    key = "global.balance"
    theta_a[key] = 0.4
    theta_b[key] = 0.1
    before = trainer.load_state().theta_current[key]
    state = trainer.record_comparison(
        design_id="bedroom_01",
        theta_a=theta_a,
        theta_b=theta_b,
        winner="A",
        features_a={"sofa_coffee_dist_m": 0.5},
        features_b={"sofa_coffee_dist_m": 0.8},
    )
    assert state.comparison_count == 1
    assert state.theta_current[key] > before


def test_trainer_tie_applies_exploration(pref_tmp):
    trainer = PreferenceTrainer("bedroom")
    theta = default_theta("bedroom")
    before = trainer.load_state().theta_current.copy()
    state = trainer.record_comparison(
        design_id="bedroom_01",
        theta_a=theta,
        theta_b=theta,
        winner="tie",
        features_a={"orphan_count": 0},
        features_b={"orphan_count": 0},
    )
    assert state.comparison_count == 1
    assert state.theta_current != before


def test_trainer_phase_label(pref_tmp):
    trainer = PreferenceTrainer("living_room")
    state = trainer.load_state()
    assert state.phase == "A"
    assert state.comparison_count < PHASE_A_LIMIT
