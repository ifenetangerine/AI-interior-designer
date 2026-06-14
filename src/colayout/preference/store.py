"""Persist golden layouts, preference comparisons, and θ state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colayout.schemas.architecture import RoomArchitecture
from colayout.schemas.layout_draft import RoomLayoutDraft

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = ROOT / "data" / "golden_layouts"
COMPARISONS_PATH = ROOT / "data" / "preference" / "comparisons.jsonl"
THETA_STATE_PATH = ROOT / "data" / "preference" / "theta_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    COMPARISONS_PATH.parent.mkdir(parents=True, exist_ok=True)


def list_golden_layouts(room_type: str | None = None) -> list[dict[str, Any]]:
    _ensure_dirs()
    out: list[dict[str, Any]] = []
    for path in GOLDEN_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if room_type and data.get("room_type") != room_type:
            continue
        out.append(
            {
                "id": data.get("id", path.stem),
                "label": data.get("label", path.stem),
                "room_type": data.get("room_type"),
                "width_m": data.get("width_m"),
                "length_m": data.get("length_m"),
                "few_shot": bool(data.get("few_shot", False)),
                "updated_at": data.get("updated_at"),
            }
        )
    out.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return out


def load_golden_layout(golden_id: str) -> dict[str, Any]:
    path = GOLDEN_DIR / f"{golden_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Golden layout not found: {golden_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_golden_layout(
    golden_id: str,
    *,
    label: str,
    room_type: str,
    width_m: float,
    length_m: float,
    draft: RoomLayoutDraft,
    architecture: RoomArchitecture | None = None,
    few_shot: bool = True,
) -> dict[str, Any]:
    _ensure_dirs()
    record = {
        "id": golden_id,
        "label": label,
        "room_type": room_type,
        "width_m": width_m,
        "length_m": length_m,
        "architecture": architecture.model_dump() if architecture else None,
        "draft": draft.model_dump(),
        "few_shot": few_shot,
        "updated_at": _now_iso(),
    }
    path = GOLDEN_DIR / f"{golden_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)
    return record


def delete_golden_layout(golden_id: str) -> None:
    path = GOLDEN_DIR / f"{golden_id}.json"
    if path.is_file():
        path.unlink()


def append_comparison(record: dict[str, Any]) -> None:
    _ensure_dirs()
    with COMPARISONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_comparisons(room_type: str | None = None) -> list[dict[str, Any]]:
    if not COMPARISONS_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in COMPARISONS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if room_type and row.get("room_type") != room_type:
            continue
        rows.append(row)
    return rows


def comparison_count_for_design(design_id: str) -> int:
    """Counted picks (A/B winners) for one cached LLM design."""
    n = 0
    for row in load_comparisons():
        rid = row.get("design_id") or row.get("golden_id")
        if rid != design_id:
            continue
        if row.get("winner") in ("A", "B"):
            n += 1
    return n


def comparison_count_for_design(design_id: str) -> int:
    """Counted picks (A/B winners) for one cached LLM design."""
    n = 0
    for row in load_comparisons():
        rid = row.get("design_id") or row.get("golden_id")
        if rid != design_id:
            continue
        if row.get("winner") in ("A", "B"):
            n += 1
    return n


def load_theta_state() -> dict[str, Any]:
    _ensure_dirs()
    if not THETA_STATE_PATH.is_file():
        return {"room_types": {}}
    return json.loads(THETA_STATE_PATH.read_text(encoding="utf-8"))


def save_theta_state(data: dict[str, Any]) -> None:
    _ensure_dirs()
    tmp = THETA_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(THETA_STATE_PATH)


def get_room_theta_state(room_type: str) -> dict[str, Any]:
    from colayout.preference.theta import default_theta

    data = load_theta_state()
    room_types = data.setdefault("room_types", {})
    if room_type not in room_types:
        room_types[room_type] = {
            "theta_current": default_theta(room_type),
            "comparison_count": 0,
        }
        save_theta_state(data)
    return room_types[room_type]


def set_room_theta_state(room_type: str, state: dict[str, Any]) -> None:
    data = load_theta_state()
    data.setdefault("room_types", {})[room_type] = state
    save_theta_state(data)
