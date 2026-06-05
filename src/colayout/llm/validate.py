"""Post-LLM validation and sanitization for room scene graphs."""

from __future__ import annotations

import logging

from colayout.catalog.kenney_index import (
    is_allowed_in_room,
    normalize_furniture_item,
)
from colayout.llm.design_rules import enrich_scene_graph
from colayout.llm.room_program import (
    check_desk_chair_balance,
    check_dining_seating,
    check_min_piece_count,
    max_furniture_pieces,
    orphan_furniture_ids,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)

logger = logging.getLogger(__name__)

MAX_FLOOR_COVERAGE = 0.65


def validate_and_sanitize(
    graph: RoomSceneGraph,
    room: RoomSpec,
) -> tuple[RoomSceneGraph, list[str]]:
    errors: list[str] = []
    max_pieces = max_furniture_pieces(room)
    furniture, furn_errors = _sanitize_furniture(
        graph.furniture, room.type, max_pieces
    )
    errors.extend(furn_errors)

    if not furniture:
        errors.append("furniture list is empty after sanitization")

    valid_ids = {f.id for f in furniture}
    constraints, constr_errors = _sanitize_constraints(graph.constraints, valid_ids)
    errors.extend(constr_errors)

    area_errors = _check_floor_coverage(furniture, room)
    errors.extend(area_errors)

    min_err = check_min_piece_count(furniture, room)
    if min_err:
        errors.append(min_err)

    desk_err = check_desk_chair_balance(furniture)
    if desk_err:
        errors.append(desk_err)

    dining_err = check_dining_seating(furniture, room)
    if dining_err:
        errors.append(dining_err)

    sanitized = RoomSceneGraph(
        room_id=graph.room_id,
        room_type=graph.room_type,
        furniture=furniture,
        constraints=constraints,
        weights=graph.weights,
    )
    sanitized = enrich_scene_graph(sanitized)

    orphans = orphan_furniture_ids(
        sanitized.furniture, sanitized.constraints, sanitized.room_type
    )
    for oid in orphans:
        item = next((f for f in sanitized.furniture if f.id == oid), None)
        cat = item.category if item else "unknown"
        errors.append(
            f"orphan furniture '{oid}' ({cat}) has no constraints — "
            "link it to anchor or zone (facing/adjacent/against_wall)"
        )

    return sanitized, errors


def _sanitize_furniture(
    items: list[FurnitureItem],
    room_type: str,
    max_pieces: int,
) -> tuple[list[FurnitureItem], list[str]]:
    errors: list[str] = []
    seen: set[str] = set()
    out: list[FurnitureItem] = []
    for item in items:
        if item.id in seen:
            errors.append(f"duplicate furniture id '{item.id}' removed")
            continue
        seen.add(item.id)
        fields, err = normalize_furniture_item(
            item.id,
            item.model_id,
            item.category,
            item.width_m,
            item.length_m,
        )
        if err or not fields:
            errors.append(err or f"invalid furniture '{item.id}' — removed")
            continue
        if not is_allowed_in_room(fields["model_id"], room_type):
            errors.append(
                f"model_id '{fields['model_id']}' not allowed in {room_type} "
                f"for '{item.id}' — removed"
            )
            continue
        if fields["category"] == "misc":
            logger.warning(
                "Furniture '%s' uses misc category for model %s",
                item.id,
                fields["model_id"],
            )
        out.append(
            FurnitureItem(
                id=fields["id"],
                model_id=fields["model_id"],
                category=fields["category"],
                width_m=fields["width_m"],
                length_m=fields["length_m"],
            )
        )
        if len(out) >= max_pieces:
            errors.append(f"truncated to {max_pieces} furniture pieces")
            break
    return out, errors


def _sanitize_constraints(
    constraints: list[FurnitureConstraint],
    valid_ids: set[str],
) -> tuple[list[FurnitureConstraint], list[str]]:
    errors: list[str] = []
    out: list[FurnitureConstraint] = []
    for c in constraints:
        if c.type == ConstraintType.ADJACENT_CHAIN:
            bad = [fid for fid in c.furniture_ids if fid not in valid_ids]
            if bad:
                errors.append(
                    f"adjacent_chain references unknown ids {bad} — dropped"
                )
                continue
            if len(c.furniture_ids) < 2:
                continue
            out.append(c)
            continue
        if c.type in (ConstraintType.AGAINST_WALL, ConstraintType.SEATS_AROUND):
            if c.furniture not in valid_ids:
                errors.append(
                    f"{c.type.value} references unknown id '{c.furniture}' — dropped"
                )
                continue
        else:
            if c.furniture_a not in valid_ids:
                errors.append(
                    f"{c.type.value} references unknown furniture_a "
                    f"'{c.furniture_a}' — dropped"
                )
                continue
            if c.furniture_b not in valid_ids:
                errors.append(
                    f"{c.type.value} references unknown furniture_b "
                    f"'{c.furniture_b}' — dropped"
                )
                continue
            if c.furniture_a == c.furniture_b:
                continue
        out.append(c)
    return out, errors


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
            f"of room floor ({furniture_area:.1f} m² / {room_area:.1f} m²); "
            "remove or resize items"
        ]
    return []
