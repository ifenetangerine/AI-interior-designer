"""Persist manual Kenney orientation labels (front_dir, wall_anchor)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LABELS_PATH = ROOT / "config" / "catalog" / "kenney_orientation_labels.json"

BACK_WALL_CATEGORIES = frozenset(
    {"counter", "fridge", "wardrobe", "tv_stand", "dresser"}
)


def _empty_store() -> dict[str, Any]:
    return {"labels": {}, "skipped": []}


@lru_cache(maxsize=1)
def load_label_store() -> dict[str, Any]:
    if not LABELS_PATH.is_file():
        return _empty_store()
    data = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    data.setdefault("labels", {})
    data.setdefault("skipped", [])
    return data


def save_label_store(data: dict[str, Any]) -> None:
    load_label_store.cache_clear()
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LABELS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(LABELS_PATH)


def get_label(model_id: str) -> dict[str, Any] | None:
    return load_label_store().get("labels", {}).get(model_id)


def get_wall_anchor(model_id: str, category: str) -> str | None:
    label = get_label(model_id)
    if label and label.get("wall_anchor"):
        return str(label["wall_anchor"])
    if category in BACK_WALL_CATEGORIES:
        return "back_center"
    return "center"


def list_skipped() -> set[str]:
    return set(load_label_store().get("skipped", []))


def is_skipped(model_id: str) -> bool:
    return model_id in list_skipped()


def save_label(
    model_id: str,
    front_dir: list[float],
    wall_anchor: str | None = None,
) -> dict[str, Any]:
    data = load_label_store()
    if model_id in data["skipped"]:
        data["skipped"] = [s for s in data["skipped"] if s != model_id]
    fx, fz = front_dir[0], front_dir[1]
    mag = (fx * fx + fz * fz) ** 0.5
    if mag < 1e-6:
        raise ValueError("front_dir must be non-zero")
    fx, fz = fx / mag, fz / mag
    entry: dict[str, Any] = {
        "front_dir": [round(fx, 4), round(fz, 4)],
        "labeled_at": datetime.now(timezone.utc).isoformat(),
    }
    if wall_anchor:
        entry["wall_anchor"] = wall_anchor
    data["labels"][model_id] = entry
    save_label_store(data)
    return entry


def skip_model(model_id: str) -> None:
    data = load_label_store()
    if model_id not in data["skipped"]:
        data["skipped"].append(model_id)
    data["labels"].pop(model_id, None)
    save_label_store(data)


def clear_label(model_id: str) -> None:
    data = load_label_store()
    data["labels"].pop(model_id, None)
    if model_id in data["skipped"]:
        data["skipped"] = [s for s in data["skipped"] if s != model_id]
    save_label_store(data)


def progress_counts(total_models: int) -> dict[str, int]:
    data = load_label_store()
    labeled = len(data.get("labels", {}))
    skipped = len(data.get("skipped", []))
    return {
        "total": total_models,
        "labeled": labeled,
        "skipped": skipped,
        "remaining": max(0, total_models - labeled - skipped),
    }
