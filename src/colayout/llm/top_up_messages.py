"""Prompt builder for the floor-coverage top-up LLM pass."""

from __future__ import annotations

import json

from colayout.catalog.kenney_index import catalog_prompt_json
from colayout.llm.floor_coverage import fcr_summary
from colayout.llm.few_shot import _trim_placement
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft


def build_top_up_user_message(room: RoomSpec, draft: RoomLayoutDraft) -> str:
    stats = fcr_summary(draft, room)
    existing = sorted(draft.placements, key=lambda p: p.placement_order)
    trimmed = [_trim_placement(p.model_dump()) for p in existing]

    lines = [
        f"Room id: {room.id}",
        f"Room type: {room.type}",
        f"Width (m): {room.width_m}",
        f"Length (m): {room.length_m}",
        f"Floor area: {stats['room_area_m2']:.2f} m²",
        "---",
        "Current floor coverage (FCR):",
        f"  Footprint on floor: {stats['footprint_m2']:.2f} m² ({stats['ratio']:.1%} of room)",
        f"  Required minimum: {stats['min_m2']:.2f} m² ({stats['min_ratio']:.0%})",
        f"  Maximum allowed: {stats['max_m2']:.2f} m² ({stats['max_ratio']:.0%})",
        f"  Deficit to close: {stats['deficit_m2']:.2f} m² of floor footprint",
        f"  Headroom before max: {stats['headroom_m2']:.2f} m²",
        "---",
        "Existing placements (do not modify — only add new pieces):",
        json.dumps({"placements": trimmed}, indent=2),
        "---",
        "Kenney catalog (pick model_id from this list):",
        catalog_prompt_json(room.type),
        "---",
        "Return JSON with an `additions` array only. "
        f"Add floor furniture until combined floor footprint reaches at least "
        f"{stats['min_m2']:.2f} m² but stays at or below {stats['max_m2']:.2f} m².",
    ]
    return "\n".join(lines)
