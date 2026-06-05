"""Orientation label store and yaw from front_dir."""

import json
from pathlib import Path

import pytest

from colayout.assets.label_store import (
    LABELS_PATH,
    clear_label,
    get_label,
    load_label_store,
    save_label,
    skip_model,
)
from colayout.assets.orientation import yaw_rest_deg_from_front_dir


def test_yaw_rest_aligns_front_to_positive_x():
    # Model-local front along +X in floor plane
    yaw = yaw_rest_deg_from_front_dir([1.0, 0.0])
    assert abs(yaw - (-90.0)) < 0.01 or abs(yaw - 270.0) < 0.01


def test_save_and_load_label(tmp_path, monkeypatch):
    path = tmp_path / "labels.json"
    monkeypatch.setattr(
        "colayout.assets.label_store.LABELS_PATH",
        path,
    )
    from colayout.assets import label_store

    label_store.load_label_store.cache_clear()
    save_label("chair", [0.0, -1.0], "center")
    entry = get_label("chair")
    assert entry is not None
    assert abs(entry["front_dir"][1] + 1.0) < 0.01
    skip_model("desk")
    data = json.loads(path.read_text())
    assert "desk" in data["skipped"]
