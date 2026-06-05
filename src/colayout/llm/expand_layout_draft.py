"""Auto-fill tier-appropriate furniture when the LLM under-delivers."""

from __future__ import annotations

from colayout.catalog.kenney_index import (
    catalog_for_room,
    is_allowed_in_room,
    load_catalog,
    role_for_model,
)
from colayout.llm.mock_layouts import load_mock_layout
from colayout.llm.room_program import (
    DECOR_BY_TIER,
    RECOMMENDED_ROLES_BY_TIER,
    REQUIRED_ROLES,
    density_tier,
    furniture_count_bounds,
    room_area_m2,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def _role_counts(placements: list[FurniturePlacementDraft]) -> dict[str, int]:
    counts: dict[str, int] = {}
    counter_segments = 0
    for p in placements:
        role = role_for_model(p.model_id)
        counts[role] = counts.get(role, 0) + 1
        if role in ("counter_end", "counter_bar", "counter_base"):
            counter_segments += 1
    if counter_segments:
        counts["counter_segment"] = counter_segments
    return counts


def _model_for_role(role: str, room_type: str) -> str | None:
    catalog = load_catalog()
    default = catalog.get("category_defaults", {}).get(role)
    if default and is_allowed_in_room(default, room_type):
        return default
    for row in catalog_for_room(room_type):
        if row["role"] == role:
            return row["id"]
    return None


def _template_by_role(room: RoomSpec) -> dict[str, dict]:
    try:
        template = load_mock_layout(room)
    except ValueError:
        return {}
    by_role: dict[str, dict] = {}
    for raw in template.get("placements", []):
        role = role_for_model(raw["model_id"])
        if role not in by_role:
            by_role[role] = raw
    return by_role


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def expand_layout_draft_for_tier(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Add missing required, recommended, and decor pieces from tier templates."""
    messages: list[str] = []
    tier = density_tier(room_area_m2(room))
    min_pieces, _ = furniture_count_bounds(room.type, tier)
    counts = _role_counts(draft.placements)
    used_ids = {p.id for p in draft.placements}
    template = _template_by_role(room)

    to_add: list[tuple[str, int]] = []
    for role, need in REQUIRED_ROLES.get(room.type, []):
        have = counts.get(role, 0)
        for _ in range(max(0, need - have)):
            to_add.append((role, 0))

    for role, need in RECOMMENDED_ROLES_BY_TIER.get(room.type, {}).get(tier, []):
        have = counts.get(role, 0)
        for _ in range(max(0, need - have)):
            to_add.append((role, 1))

    for role, need in DECOR_BY_TIER.get(room.type, {}).get(tier, []):
        have = counts.get(role, 0)
        for _ in range(max(0, need - have)):
            to_add.append((role, 2))

    filler_roles = ("side_table", "lamp", "plant", "chair")
    filler_idx = 0
    while len(draft.placements) + len(to_add) < min_pieces:
        role = filler_roles[filler_idx % len(filler_roles)]
        if _model_for_role(role, room.type):
            to_add.append((role, 3))
        filler_idx += 1
        if filler_idx > 12:
            break

    if not to_add:
        return draft, messages

    new_placements = list(draft.placements)
    next_order = max((p.placement_order for p in new_placements), default=0) + 1

    for role, _prio in to_add:
        model_id = _model_for_role(role, room.type)
        if not model_id:
            continue
        tpl = template.get(role)
        if tpl:
            fid = _unique_id(tpl["id"], used_ids)
            cx = float(tpl["center_x_m"])
            cz = float(tpl["center_z_m"])
            orient = int(tpl.get("orientation", 0))
            rel = tpl.get("relative_to")
            mid = tpl["model_id"]
            if is_allowed_in_room(mid, room.type):
                model_id = mid
        else:
            fid = _unique_id(role.replace("_", ""), used_ids)
            cx = room.width_m * 0.5
            cz = room.length_m * 0.5
            orient = 0
            rel = None

        new_placements.append(
            FurniturePlacementDraft(
                id=fid,
                model_id=model_id,
                placement_order=next_order,
                center_x_m=cx,
                center_z_m=cz,
                orientation=orient,
                relative_to=rel,
                note=f"auto-added for {tier} tier",
            )
        )
        used_ids.add(fid)
        counts[role] = counts.get(role, 0) + 1
        next_order += 1
        messages.append(f"(info) auto-added {role} as '{fid}' for {tier} {room.type}")

    return draft.model_copy(update={"placements": new_placements}), messages
