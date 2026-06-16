"""Shared LLM placement prompt builders and JSON parsing."""

from __future__ import annotations

import json
import re

from colayout.catalog.kenney_index import catalog_prompt_json
from colayout.llm.few_shot import format_few_shot_block
from colayout.llm.room_program import (
    anchor_category,
    density_tier,
    floor_coverage_ratio_bounds,
    furniture_count_bounds,
    room_area_m2,
)
from colayout.schemas.floor import RoomSpec


def parse_llm_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def build_placement_user_message(
    room: RoomSpec,
    *,
    exclude_golden_ids: set[str] | frozenset[str] | None = None,
) -> str:
    area = room_area_m2(room)
    tier = density_tier(area)
    min_p, max_p = furniture_count_bounds(room.type, tier)
    fcr_min_m2, fcr_max_m2 = floor_coverage_ratio_bounds(area)
    few_shot = format_few_shot_block(room, exclude_ids=exclude_golden_ids)
    parts = [
        f"Room id: {room.id}",
        f"Room type: {room.type}",
        f"Width (m): {room.width_m}",
        f"Length (m): {room.length_m}",
        f"Floor area: {area:.1f} m²",
        f"Target floor coverage (FCR): {fcr_min_m2:.1f}–{fcr_max_m2:.1f} m² "
        f"(35–45% of floor area; sum of furniture footprint areas)",
        f"Density tier: {tier}",
        f"Target furniture count: {min_p}–{max_p} pieces",
        f"Primary anchor role: {anchor_category(room.type)}",
        f"Preferences: {room.preferences or 'none'}",
        "---",
    ]
    if few_shot:
        parts.extend([few_shot, "---"])
    else:
        parts.append(
            "No few-shot examples for this room type — use sensible staging for the tier."
        )
        parts.append("---")
    parts.extend(
        [
            "Kenney catalog (pick model_id from this list):",
            catalog_prompt_json(room.type),
            "---",
            "Return the full layout JSON with explicit center_x_m, center_z_m, orientation. "
            "Keep total furniture footprint area within the FCR target range.",
        ]
    )
    return "\n".join(parts)
