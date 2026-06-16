"""Snap LLM placement drafts onto walls (anchors and storage)."""

from __future__ import annotations

from colayout.catalog.kenney_index import placement_category, role_for_model
from colayout.llm.draft_to_hints import footprint_m_for_placement
from colayout.llm.room_program import (
    ANCHOR_WALL_BY_ROOM,
    COUNTER_SEGMENT_ROLES,
    FLOATING_ANCHOR_ROLES,
    anchor_category,
    default_wall_for_category,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

WALL_MARGIN_M = 0.06
COUNTER_WALL_MARGIN_M = 0.02

WALL_HUG_ROLES = frozenset(
    {
        "bed",
        "wardrobe",
        "dresser",
        "fridge",
        "sink",
        "stove",
        "tv_stand",
        "tv_console",
        "storage_cabinet",
        "desk",
    }
) | COUNTER_SEGMENT_ROLES


def _orientation_for_wall(wall: str) -> int:
    return 1 if wall in ("west", "east") else 0


def _snap_center_to_wall(
    cx: float,
    cz: float,
    fw: float,
    fl: float,
    wall: str,
    room_w: float,
    room_l: float,
    *,
    margin_m: float = WALL_MARGIN_M,
) -> tuple[float, float]:
    if wall == "west":
        cx = fw / 2 + margin_m
    elif wall == "east":
        cx = room_w - fw / 2 - margin_m
    elif wall == "south":
        cz = fl / 2 + margin_m
    elif wall == "north":
        cz = room_l - fl / 2 - margin_m
    return cx, cz


def _clamp_center(
    cx: float,
    cz: float,
    fw: float,
    fl: float,
    room_w: float,
    room_l: float,
) -> tuple[float, float]:
    cx = max(fw / 2, min(cx, room_w - fw / 2))
    cz = max(fl / 2, min(cz, room_l - fl / 2))
    return cx, cz


def _wall_for_placement(
    p: FurniturePlacementDraft,
    room: RoomSpec,
) -> str | None:
    role = role_for_model(p.model_id)
    anchor_role = anchor_category(room.type)

    if role in FLOATING_ANCHOR_ROLES:
        return None

    if p.placement_order == 1 and role == anchor_role:
        if role in FLOATING_ANCHOR_ROLES:
            return None
        return ANCHOR_WALL_BY_ROOM.get(room.type)

    if role in WALL_HUG_ROLES:
        cat = placement_category(p.model_id)
        return default_wall_for_category(cat, room.type)

    cat = placement_category(p.model_id)
    if cat in (
        "wardrobe",
        "dresser",
        "fridge",
        "counter",
        "tv_stand",
        "tv_console",
        "storage_cabinet",
        "desk",
    ):
        return default_wall_for_category(cat, room.type)
    return None


def _follows_parent_offset(p: FurniturePlacementDraft, room: RoomSpec) -> bool:
    """Children that should keep their offset from relative_to after parent moves."""
    if p.on_surface_of and role_for_model(p.model_id) == "tv":
        return True
    if not p.relative_to:
        return False
    role = role_for_model(p.model_id)
    if role in WALL_HUG_ROLES:
        return False
    if _wall_for_placement(p, room):
        return False
    return True


def _snap_single(
    p: FurniturePlacementDraft,
    room: RoomSpec,
) -> FurniturePlacementDraft:
    """Snap one independent piece to its wall (or clamp only)."""
    updated = p.model_copy()
    wall = _wall_for_placement(updated, room)
    fw, fl = footprint_m_for_placement(updated)

    if not wall or wall not in ("west", "east", "south", "north"):
        cx, cz = _clamp_center(
            updated.center_x_m,
            updated.center_z_m,
            fw,
            fl,
            room.width_m,
            room.length_m,
        )
        return updated.model_copy(
            update={"center_x_m": round(cx, 3), "center_z_m": round(cz, 3)}
        )

    role = role_for_model(updated.model_id)
    cat = placement_category(updated.model_id)
    if role in ("bed", "sofa") or (
        updated.placement_order == 1 and role == anchor_category(room.type)
    ):
        updated = updated.model_copy(
            update={"orientation": _orientation_for_wall(wall)}
        )
    elif role in COUNTER_SEGMENT_ROLES or cat == "counter":
        updated = updated.model_copy(
            update={"orientation": _orientation_for_wall(wall)}
        )

    margin = (
        COUNTER_WALL_MARGIN_M
        if role in COUNTER_SEGMENT_ROLES or cat == "counter"
        else WALL_MARGIN_M
    )
    cx, cz = _snap_center_to_wall(
        updated.center_x_m,
        updated.center_z_m,
        fw,
        fl,
        wall,
        room.width_m,
        room.length_m,
        margin_m=margin,
    )
    cx, cz = _clamp_center(cx, cz, fw, fl, room.width_m, room.length_m)
    return updated.model_copy(
        update={
            "center_x_m": round(cx, 3),
            "center_z_m": round(cz, 3),
        }
    )


def snap_placements_to_walls(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> RoomLayoutDraft:
    """Snap wall-hug pieces; children with relative_to follow parent offsets."""
    placements = sorted(draft.placements, key=lambda p: p.placement_order)
    original = {p.id: (p.center_x_m, p.center_z_m) for p in placements}
    by_id = {p.id: p for p in placements}
    snapped: dict[str, FurniturePlacementDraft] = {}

    for p in placements:
        if _follows_parent_offset(p, room):
            continue
        snapped[p.id] = _snap_single(p, room)

    for p in placements:
        if p.id in snapped:
            continue
        if p.on_surface_of and role_for_model(p.model_id) == "tv":
            parent = snapped.get(p.on_surface_of) or by_id.get(p.on_surface_of)
            if parent:
                snapped[p.id] = p.model_copy(
                    update={
                        "center_x_m": round(parent.center_x_m, 3),
                        "center_z_m": round(parent.center_z_m, 3),
                        "on_surface_of": p.on_surface_of,
                    }
                )
                continue
        parent_id = p.relative_to
        if not parent_id or not _follows_parent_offset(p, room):
            snapped[p.id] = _snap_single(p, room)
            continue
        if parent_id not in original:
            snapped[p.id] = _snap_single(p, room)
            continue
        parent = snapped.get(parent_id)
        if not parent:
            snapped[p.id] = _snap_single(p, room)
            continue
        ox = original[p.id][0] - original[parent_id][0]
        oz = original[p.id][1] - original[parent_id][1]
        fw, fl = footprint_m_for_placement(p)
        cx = parent.center_x_m + ox
        cz = parent.center_z_m + oz
        cx, cz = _clamp_center(cx, cz, fw, fl, room.width_m, room.length_m)
        snapped[p.id] = p.model_copy(
            update={
                "center_x_m": round(cx, 3),
                "center_z_m": round(cz, 3),
            }
        )

    return draft.model_copy(update={"placements": list(snapped.values())})
