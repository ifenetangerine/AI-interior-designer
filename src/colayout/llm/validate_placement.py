"""Validate and sanitize LLM layout drafts."""

from __future__ import annotations

from colayout.catalog.kenney_index import (
    footprint_for_model,
    is_allowed_in_room,
    placement_category,
)
from colayout.llm.draft_to_hints import footprint_m_for_placement
from colayout.llm.mock_layouts import _footprint_m
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.expand_layout_draft import expand_layout_draft_for_tier
from colayout.llm.validate_principles import validate_design_principles
from colayout.llm.snap_placement import snap_placements_to_walls
from colayout.llm.room_program import (
    check_decor_staging,
    check_desk_chair_balance,
    check_dining_seating,
    check_floor_coverage_min,
    check_min_piece_count,
    check_recommended_roles,
    check_required_furniture,
    max_furniture_pieces,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.scene import FurnitureItem

MAX_FLOOR_COVERAGE = 0.65


def validate_layout_draft(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> tuple[RoomLayoutDraft, list[str]]:
    errors: list[str] = []
    max_pieces = max_furniture_pieces(room)
    placements, place_errors = _sanitize_placements(
        draft.placements, room.type, room, max_pieces
    )
    errors.extend(place_errors)

    if not placements:
        errors.append("placements list is empty after sanitization")
        return draft.model_copy(update={"placements": []}), errors

    draft = draft.model_copy(update={"placements": placements})
    draft, expand_msgs = expand_layout_draft_for_tier(draft, room)
    errors.extend(expand_msgs)
    placements = list(draft.placements)

    order_errors = _check_placement_orders(placements)
    errors.extend(order_errors)

    bounds_errors = _check_bounds(placements, room)
    errors.extend(bounds_errors)

    overlap_errors = _check_overlaps(placements)
    for e in overlap_errors:
        errors.append(e)

    furniture = [
        FurnitureItem(
            id=p.id,
            model_id=p.model_id,
            category=placement_category(p.model_id),
            width_m=footprint_for_model(p.model_id)[0],
            length_m=footprint_for_model(p.model_id)[1],
        )
        for p in placements
    ]

    required_errs = check_required_furniture(
        [p.model_id for p in placements], room.type
    )
    errors.extend(required_errs)

    min_err = check_min_piece_count(furniture, room)
    if min_err:
        errors.append(min_err)

    area_errors = _check_floor_coverage(furniture, room)
    errors.extend(area_errors)

    desk_err = check_desk_chair_balance(furniture)
    if desk_err:
        errors.append(f"(warning) {desk_err}")

    dining_err = check_dining_seating(furniture, room)
    if dining_err:
        errors.append(f"(warning) {dining_err}")

    model_ids = [p.model_id for p in placements]
    errors.extend(check_recommended_roles(model_ids, room))
    errors.extend(check_decor_staging(model_ids, room))

    coverage_min = check_floor_coverage_min(furniture, room)
    if coverage_min:
        errors.append(coverage_min)

    sorted_placements = sorted(placements, key=lambda p: p.placement_order)
    sanitized = draft.model_copy(update={"placements": sorted_placements})
    snapped = snap_placements_to_walls(sanitized, room)
    graph = draft_to_scene_graph(snapped, room)
    errors.extend(
        validate_design_principles(
            snapped.placements, room, graph.furniture, graph.constraints
        )
    )
    return snapped, errors


def _sanitize_placements(
    items: list[FurniturePlacementDraft],
    room_type: str,
    room: RoomSpec,
    max_pieces: int,
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    errors: list[str] = []
    seen: set[str] = set()
    out: list[FurniturePlacementDraft] = []

    for item in items:
        if item.id in seen:
            errors.append(f"duplicate placement id '{item.id}' removed")
            continue
        if not is_allowed_in_room(item.model_id, room_type):
            errors.append(
                f"model_id '{item.model_id}' not allowed in {room_type} "
                f"for '{item.id}' — removed"
            )
            continue
        seen.add(item.id)
        orient = 1 if item.orientation in (1, 3) else 0
        fw, fl = _footprint_m(item.model_id, orient)
        min_x, max_x = fw / 2, room.width_m - fw / 2
        min_z, max_z = fl / 2, room.length_m - fl / 2
        cx = max(min_x, min(item.center_x_m, max_x)) if max_x >= min_x else room.width_m / 2
        cz = max(min_z, min(item.center_z_m, max_z)) if max_z >= min_z else room.length_m / 2
        if abs(cx - item.center_x_m) > 0.01 or abs(cz - item.center_z_m) > 0.01:
            errors.append(f"clamped center for '{item.id}' to room bounds")
        out.append(
            item.model_copy(
                update={
                    "center_x_m": cx,
                    "center_z_m": cz,
                    "orientation": 1 if item.orientation in (1, 3) else 0,
                }
            )
        )
        if len(out) >= max_pieces:
            errors.append(f"truncated to {max_pieces} placements")
            break

    return out, errors


def _check_placement_orders(placements: list[FurniturePlacementDraft]) -> list[str]:
    errors: list[str] = []
    orders = [p.placement_order for p in placements]
    if min(orders) != 1:
        errors.append("placement_order must start at 1")
    if len(orders) != len(set(orders)):
        errors.append("duplicate placement_order values")
    return errors


def _check_bounds(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> list[str]:
    errors: list[str] = []
    for p in placements:
        w_m, l_m = footprint_m_for_placement(p)
        half_w, half_l = w_m / 2, l_m / 2
        if p.center_x_m - half_w < -0.05:
            errors.append(
                f"'{p.id}' extends west of room (center_x={p.center_x_m:.2f})"
            )
        if p.center_x_m + half_w > room.width_m + 0.05:
            errors.append(
                f"'{p.id}' extends east of room (center_x={p.center_x_m:.2f})"
            )
        if p.center_z_m - half_l < -0.05:
            errors.append(
                f"'{p.id}' extends south of room (center_z={p.center_z_m:.2f})"
            )
        if p.center_z_m + half_l > room.length_m + 0.05:
            errors.append(
                f"'{p.id}' extends north of room (center_z={p.center_z_m:.2f})"
            )
    return errors


def _aabb_overlap(
    a: FurniturePlacementDraft,
    b: FurniturePlacementDraft,
) -> bool:
    aw, al = footprint_m_for_placement(a)
    bw, bl = footprint_m_for_placement(b)
    a_x0, a_x1 = a.center_x_m - aw / 2, a.center_x_m + aw / 2
    a_z0, a_z1 = a.center_z_m - al / 2, a.center_z_m + al / 2
    b_x0, b_x1 = b.center_x_m - bw / 2, b.center_x_m + bw / 2
    b_z0, b_z1 = b.center_z_m - bl / 2, b.center_z_m + bl / 2
    tol = 0.02
    return (
        a_x0 < b_x1 - tol
        and a_x1 > b_x0 + tol
        and a_z0 < b_z1 - tol
        and a_z1 > b_z0 + tol
    )


def _allowed_stack_pairs(
    placements: list[FurniturePlacementDraft],
) -> set[frozenset[str]]:
    by_id = {p.id: p for p in placements}
    allowed: set[frozenset[str]] = set()
    for p in placements:
        parent = p.on_surface_of
        if not parent and p.relative_to:
            from colayout.llm.draft_to_hints import _resolve_surface_parent

            parent = _resolve_surface_parent(p, by_id)
        if parent and parent in by_id:
            allowed.add(frozenset({p.id, parent}))
    return allowed


def _check_overlaps(placements: list[FurniturePlacementDraft]) -> list[str]:
    errors: list[str] = []
    allowed = _allowed_stack_pairs(placements)
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            if frozenset({a.id, b.id}) in allowed:
                continue
            if _aabb_overlap(a, b):
                errors.append(
                    f"overlap between '{a.id}' and '{b.id}' — IP refine will adjust"
                )
    return errors


def _check_floor_coverage(
    furniture: list[FurnitureItem],
    room: RoomSpec,
) -> list[str]:
    if not furniture:
        return []
    room_area = room.width_m * room.length_m
    if room_area <= 0:
        return ["room dimensions must be positive"]
    furniture_area = sum(
        (f.width_m or 0) * (f.length_m or 0) for f in furniture
    )
    ratio = furniture_area / room_area
    if ratio > MAX_FLOOR_COVERAGE:
        return [
            f"furniture footprint {ratio:.0%} exceeds {MAX_FLOOR_COVERAGE:.0%} "
            f"of room floor ({furniture_area:.1f} m² / {room_area:.1f} m²)"
        ]
    return []


def is_retry_pressure_error(msg: str) -> bool:
    """Non-blocking warnings that should trigger LLM repair attempts."""
    lower = msg.lower()
    if "(warning)" not in lower:
        return False
    return any(
        k in lower
        for k in (
            "below",
            "missing recommended",
            "missing staging",
            "footprint",
            "balance",
            "proportion",
            "rhythm",
            "structure",
        )
    )


def is_blocking_placement_error(msg: str) -> bool:
    lower = msg.lower()
    if "(warning)" in lower:
        return False
    if "overlap" in lower and "ip refine" in lower:
        return False
    if "empty" in lower:
        return True
    if "exceeds" in lower and "floor" in lower:
        return True
    if "below minimum" in lower:
        return True
    if "missing required" in lower:
        return True
    if "extends" in lower:
        return True
    if "not allowed" in lower:
        return True
    if "placement_order" in lower:
        return True
    if "placements list is empty" in lower:
        return True
    return False
