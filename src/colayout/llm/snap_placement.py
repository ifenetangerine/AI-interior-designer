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

WALL_HUG_ROLES = frozenset(
    {
        "bed",
        "wardrobe",
        "dresser",
        "fridge",
        "sink",
        "stove",
        "tv_stand",
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
) -> tuple[float, float]:
    if wall == "west":
        cx = fw / 2 + WALL_MARGIN_M
    elif wall == "east":
        cx = room_w - fw / 2 - WALL_MARGIN_M
    elif wall == "south":
        cz = fl / 2 + WALL_MARGIN_M
    elif wall == "north":
        cz = room_l - fl / 2 - WALL_MARGIN_M
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
    if cat in ("wardrobe", "dresser", "fridge", "counter", "tv_stand", "desk"):
        return default_wall_for_category(cat, room.type)
    return None


def snap_placements_to_walls(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> RoomLayoutDraft:
    """Enforce wall-backed positions for wall-hug roles; floating anchors unchanged."""
    snapped: list[FurniturePlacementDraft] = []

    for p in draft.placements:
        updated = p.model_copy()
        wall = _wall_for_placement(updated, room)
        if not wall or wall not in ("west", "east", "south", "north"):
            snapped.append(updated)
            continue

        role = role_for_model(updated.model_id)
        if role in ("bed", "sofa") or (
            updated.placement_order == 1
            and role == anchor_category(room.type)
        ):
            updated = updated.model_copy(
                update={"orientation": _orientation_for_wall(wall)}
            )

        fw, fl = footprint_m_for_placement(updated)
        cx, cz = _snap_center_to_wall(
            updated.center_x_m,
            updated.center_z_m,
            fw,
            fl,
            wall,
            room.width_m,
            room.length_m,
        )
        cx, cz = _clamp_center(cx, cz, fw, fl, room.width_m, room.length_m)
        snapped.append(
            updated.model_copy(
                update={
                    "center_x_m": round(cx, 3),
                    "center_z_m": round(cz, 3),
                }
            )
        )

    return draft.model_copy(update={"placements": snapped})
