"""Format golden layouts as few-shot examples for the LLM planner."""

from __future__ import annotations

import json
from typing import Any

from colayout.preference.store import list_golden_layouts, load_golden_layout
from colayout.schemas.floor import RoomSpec

_MAX_PLACEMENTS_IN_EXAMPLE = 24


def few_shot_golden_ids(
    room_type: str,
    *,
    exclude_ids: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Golden layout ids marked few_shot for a room type, newest first."""
    skip = exclude_ids or set()
    rows = list_golden_layouts(room_type)
    shot = [r for r in rows if r.get("few_shot") and r["id"] not in skip]
    shot.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return [r["id"] for r in shot]


def _trim_placement(p: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": p["id"],
        "model_id": p["model_id"],
        "placement_order": p["placement_order"],
        "center_x_m": round(float(p["center_x_m"]), 2),
        "center_z_m": round(float(p["center_z_m"]), 2),
        "orientation": int(p.get("orientation", 0)),
    }
    if p.get("relative_to"):
        out["relative_to"] = p["relative_to"]
    if p.get("on_surface_of"):
        out["on_surface_of"] = p["on_surface_of"]
    if p.get("composition_role"):
        out["composition_role"] = p["composition_role"]
    if p.get("zone"):
        out["zone"] = p["zone"]
    if p.get("note"):
        out["note"] = p["note"]
    return out


def _example_payload(record: dict[str, Any]) -> dict[str, Any]:
    draft = record.get("draft") or {}
    placements = sorted(
        draft.get("placements") or [],
        key=lambda p: p.get("placement_order", 0),
    )[:_MAX_PLACEMENTS_IN_EXAMPLE]
    return {
        "label": record.get("label") or record.get("id"),
        "room_type": record.get("room_type"),
        "width_m": record.get("width_m"),
        "length_m": record.get("length_m"),
        "placements": [_trim_placement(p) for p in placements],
    }


def load_few_shot_examples(
    room_type: str,
    *,
    exclude_ids: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for gid in few_shot_golden_ids(room_type, exclude_ids=exclude_ids):
        try:
            record = load_golden_layout(gid)
        except FileNotFoundError:
            continue
        examples.append(_example_payload(record))
    return examples


def format_few_shot_block(
    room: RoomSpec,
    *,
    exclude_ids: set[str] | frozenset[str] | None = None,
) -> str:
    """Prompt section with golden few-shot layout examples (empty if none)."""
    examples = load_few_shot_examples(room.type, exclude_ids=exclude_ids)
    if not examples:
        return ""
    lines = [
        "Few-shot reference layouts (match this structure and style; adapt to target size):",
    ]
    for i, ex in enumerate(examples, start=1):
        lines.append(
            f"Example {i}: {ex['label']} — {ex['room_type']} "
            f"{ex['width_m']}×{ex['length_m']} m"
        )
        lines.append(json.dumps({"placements": ex["placements"]}, indent=2))
    lines.append(
        "Mirror these examples: anchor tagging, relative_to chains, symmetry, "
        "model_id choices, and staging density."
    )
    return "\n".join(lines)
