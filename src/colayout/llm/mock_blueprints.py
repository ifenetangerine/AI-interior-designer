"""Tier-1 mock hierarchical blueprints (offline / MockLLMProvider)."""

from __future__ import annotations

from pathlib import Path

import yaml

from colayout.llm.room_program import density_tier, room_area_m2
from colayout.placement.blueprint_expand import room_blueprint_from_dict
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_blueprint import RoomLayoutBlueprint

ROOT = Path(__file__).resolve().parents[3]
BLUEPRINTS_PATH = ROOT / "config" / "catalog" / "mock_room_blueprints.yaml"

REF_ROOM_M: dict[str, tuple[float, float]] = {
    "bedroom": (4.0, 3.5),
    "living_room": (4.0, 3.5),
    "kitchen": (5.0, 4.0),
}


def _scale_node_centers(nodes: list[dict], room: RoomSpec) -> list[dict]:
    ref_w, ref_l = REF_ROOM_M.get(room.type, (room.width_m, room.length_m))
    if ref_w <= 0 or ref_l <= 0:
        return [dict(n) for n in nodes]
    sx = room.width_m / ref_w
    sz = room.length_m / ref_l
    scaled: list[dict] = []
    for raw in nodes:
        node = dict(raw)
        if node.get("kind") in ("compound_group", "standalone_asset"):
            node["center_x_m"] = float(node.get("center_x_m", 0.0)) * sx
            node["center_z_m"] = float(node.get("center_z_m", 0.0)) * sz
        scaled.append(node)
    return scaled


def load_mock_blueprint(room: RoomSpec) -> RoomLayoutBlueprint:
    with BLUEPRINTS_PATH.open(encoding="utf-8") as f:
        layouts = yaml.safe_load(f)
    room_layouts = layouts.get(room.type)
    if not room_layouts:
        raise ValueError(f"No mock blueprints for room type '{room.type}'")
    tier = density_tier(room_area_m2(room))
    kit = room_layouts.get(tier) or room_layouts.get("standard")
    if not kit:
        raise ValueError(f"No mock blueprint for {room.type} tier {tier}")
    nodes = _scale_node_centers(list(kit.get("nodes", [])), room)
    return room_blueprint_from_dict(
        {
            "room_id": room.id,
            "room_type": room.type,
            "nodes": nodes,
            "weights": dict(kit.get("weights", {"rel": 0.2, "bal": 0.0, "walk": 0.1})),
        }
    )
