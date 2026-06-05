"""Load room template YAML files as LLM design baselines."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT / "config" / "room_templates"
DEFAULT_BASELINE_TYPE = "bedroom"


def list_supported_types() -> list[str]:
    if not TEMPLATE_DIR.is_dir():
        return [DEFAULT_BASELINE_TYPE]
    return sorted(p.stem for p in TEMPLATE_DIR.glob("*.yaml"))


def load_baseline(room_type: str) -> dict:
    path = TEMPLATE_DIR / f"{room_type}.yaml"
    if not path.exists():
        path = TEMPLATE_DIR / f"{DEFAULT_BASELINE_TYPE}.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid baseline YAML: {path}")
    return data


def baseline_to_prompt_json(baseline: dict) -> str:
    payload = {
        "room_type": baseline.get("room_type"),
        "furniture": baseline.get("furniture", []),
        "constraints": baseline.get("constraints", []),
        "weights": baseline.get("weights", {"rel": 1.0, "bal": 0.5, "walk": 0.1}),
    }
    return json.dumps(payload, indent=2)
