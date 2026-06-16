"""3-tier layout pipeline: hierarchical intent → procedural expand → flat draft."""

from __future__ import annotations

import os

from colayout.placement.blueprint_expand import (
    ExpandedLayout,
    expand_room_blueprint,
    room_blueprint_from_dict,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_blueprint import RoomLayoutBlueprint


def use_blueprint_pipeline() -> bool:
    return os.getenv("COLAYOUT_BLUEPRINTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def expand_blueprint_intent(
    blueprint: RoomLayoutBlueprint,
    *,
    cell_m: float = 0.25,
) -> ExpandedLayout:
    """Tier 2: procedural expansion into flat draft + compound group plans."""
    return expand_room_blueprint(blueprint, cell_m=cell_m)


def layout_from_hierarchical_json(
    data: dict,
    room: RoomSpec,
    *,
    cell_m: float = 0.25,
) -> ExpandedLayout:
    """Tier 1 parse: accept hierarchical JSON with compound_group / standalone_asset."""
    payload = dict(data)
    payload.setdefault("room_id", room.id)
    payload.setdefault("room_type", room.type)
    blueprint = room_blueprint_from_dict(payload)
    return expand_blueprint_intent(blueprint, cell_m=cell_m)
