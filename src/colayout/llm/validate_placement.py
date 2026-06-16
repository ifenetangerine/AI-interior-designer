"""Sanitize LLM layout drafts (minimal fixes, no blocking tier expansion)."""

from __future__ import annotations

from colayout.catalog.fix_model_id import fix_model_id
from colayout.catalog.kenney_index import (
    is_stackable_child_role,
    is_valid_surface_stack,
    role_for_model,
)
from colayout.llm.draft_to_hints import (
    auto_link_overlapping_stacks,
    footprint_m_for_placement,
)
from colayout.llm.anchor_structure import repair_tv_viewing_stack
from colayout.llm.mock_layouts import _footprint_m
from colayout.llm.snap_placement import snap_placements_to_walls
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def validate_layout_draft(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Light sanitization for LLM output: fix ids, renumber, clamp, stack links."""
    messages: list[str] = []
    placements = list(draft.placements)

    placements, fix_msgs = _fix_model_ids(placements, room.type)
    messages.extend(fix_msgs)

    placements, id_msgs = _dedupe_ids(placements)
    messages.extend(id_msgs)

    if not placements:
        messages.append("(warning) placements list is empty after sanitization")
        return draft.model_copy(update={"placements": []}), messages

    placements = _renumber_placement_orders(placements)
    placements, clamp_msgs = _clamp_placements(placements, room)
    messages.extend(clamp_msgs)

    snapped = snap_placements_to_walls(
        draft.model_copy(update={"placements": placements}),
        room,
    )
    placements = list(snapped.placements)

    repaired = repair_tv_viewing_stack(
        draft.model_copy(update={"placements": placements}),
        room,
    )
    placements = list(repaired.placements)

    placements, surface_msgs = _sanitize_on_surface_of(placements)
    messages.extend(surface_msgs)
    placements = auto_link_overlapping_stacks(placements)

    sorted_placements = sorted(placements, key=lambda p: p.placement_order)
    return draft.model_copy(update={"placements": sorted_placements}), messages


def validate_golden_layout_draft(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Validate author layouts without auto-fixing model ids."""
    errors: list[str] = []
    from colayout.catalog.kenney_index import is_allowed_in_room

    placements, place_errors = _sanitize_placements_strict(
        draft.placements, room.type, room
    )
    errors.extend(place_errors)

    if not placements:
        errors.append("placements list is empty after sanitization")
        return draft.model_copy(update={"placements": []}), errors

    placements, surface_msgs = _sanitize_on_surface_of(placements)
    errors.extend(surface_msgs)
    placements = auto_link_overlapping_stacks(placements)
    placements = _renumber_placement_orders(placements)

    sorted_placements = sorted(placements, key=lambda p: p.placement_order)
    return draft.model_copy(update={"placements": sorted_placements}), errors


def _fix_model_ids(
    items: list[FurniturePlacementDraft],
    room_type: str,
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    messages: list[str] = []
    out: list[FurniturePlacementDraft] = []
    for item in items:
        fixed, changed = fix_model_id(item.model_id, room_type)
        if not fixed:
            messages.append(
                f"(warning) dropped '{item.id}': unresolvable model_id '{item.model_id}'"
            )
            continue
        if changed:
            messages.append(
                f"(info) fixed model_id '{item.model_id}' → '{fixed}' for '{item.id}'"
            )
        out.append(item.model_copy(update={"model_id": fixed}))
    return out, messages


def _dedupe_ids(
    items: list[FurniturePlacementDraft],
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    messages: list[str] = []
    seen: set[str] = set()
    out: list[FurniturePlacementDraft] = []
    for item in items:
        if item.id in seen:
            messages.append(f"(info) duplicate placement id '{item.id}' removed")
            continue
        seen.add(item.id)
        out.append(item)
    return out, messages


def _renumber_placement_orders(
    placements: list[FurniturePlacementDraft],
) -> list[FurniturePlacementDraft]:
    ordered = sorted(placements, key=lambda p: p.placement_order)
    return [
        p.model_copy(update={"placement_order": i})
        for i, p in enumerate(ordered, start=1)
    ]


def _clamp_placements(
    items: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    messages: list[str] = []
    out: list[FurniturePlacementDraft] = []
    for item in items:
        orient = 1 if item.orientation in (1, 3) else 0
        fw, fl = _footprint_m(item.model_id, orient)
        min_x, max_x = fw / 2, room.width_m - fw / 2
        min_z, max_z = fl / 2, room.length_m - fl / 2
        cx = max(min_x, min(item.center_x_m, max_x)) if max_x >= min_x else room.width_m / 2
        cz = max(min_z, min(item.center_z_m, max_z)) if max_z >= min_z else room.length_m / 2
        if abs(cx - item.center_x_m) > 0.01 or abs(cz - item.center_z_m) > 0.01:
            messages.append(f"(info) clamped center for '{item.id}' to room bounds")
        out.append(
            item.model_copy(
                update={
                    "center_x_m": cx,
                    "center_z_m": cz,
                    "orientation": orient,
                }
            )
        )
    return out, messages


def _sanitize_placements_strict(
    items: list[FurniturePlacementDraft],
    room_type: str,
    room: RoomSpec,
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    from colayout.catalog.kenney_index import is_allowed_in_room

    errors: list[str] = []
    seen: set[str] = set()
    out: list[FurniturePlacementDraft] = []

    for item in items:
        if item.id in seen:
            errors.append(f"duplicate placement id '{item.id}' removed")
            continue
        if not is_allowed_in_room(item.model_id, room_type):
            errors.append(
                f"unknown model_id '{item.model_id}' for '{item.id}' — removed"
            )
            continue
        seen.add(item.id)
        fw, fl = footprint_m_for_placement(item)
        orient = item.orientation
        cx, cz = item.center_x_m, item.center_z_m
        out.append(item.model_copy(update={"center_x_m": cx, "center_z_m": cz}))
    return out, errors


def _sanitize_on_surface_of(
    placements: list[FurniturePlacementDraft],
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    by_id = {p.id: p for p in placements}
    msgs: list[str] = []
    out: list[FurniturePlacementDraft] = []
    for p in placements:
        if not p.on_surface_of:
            out.append(p)
            continue
        parent = by_id.get(p.on_surface_of)
        if parent is None:
            msgs.append(
                f"(info) removed on_surface_of '{p.on_surface_of}' for '{p.id}'"
            )
            out.append(p.model_copy(update={"on_surface_of": None}))
            continue
        child_role = role_for_model(p.model_id)
        if child_role != "tv" and not is_stackable_child_role(child_role):
            msgs.append(f"(info) removed on_surface_of for '{p.id}'")
            out.append(p.model_copy(update={"on_surface_of": None}))
            continue
        if not is_valid_surface_stack(p.model_id, parent.model_id):
            msgs.append(f"(info) removed invalid stack for '{p.id}'")
            out.append(p.model_copy(update={"on_surface_of": None}))
            continue
        out.append(p)
    return out, msgs


def is_blocking_placement_error(msg: str) -> bool:
    """LLM sanitization no longer produces blocking errors."""
    return False


def is_retry_pressure_error(msg: str) -> bool:
    return False
