"""Load deterministic mock room kits from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from colayout.llm.room_program import density_tier, room_area_m2
from colayout.schemas.floor import RoomSpec

ROOT = Path(__file__).resolve().parents[3]
KITS_PATH = ROOT / "config" / "catalog" / "mock_room_kits.yaml"


def load_mock_kit(room: RoomSpec) -> dict:
    with KITS_PATH.open(encoding="utf-8") as f:
        kits = yaml.safe_load(f)
    room_kits = kits.get(room.type)
    if not room_kits:
        raise ValueError(f"No mock kits for room type '{room.type}'")
    tier = density_tier(room_area_m2(room))
    kit = room_kits.get(tier) or room_kits.get("standard")
    if not kit:
        raise ValueError(f"No mock kit for {room.type} tier {tier}")
    return {
        "room_type": room.type,
        "furniture": list(kit.get("furniture", [])),
        "constraints": list(kit.get("constraints", [])),
        "weights": dict(kit.get("weights", {"rel": 1.0, "bal": 0.0, "walk": 0.7})),
    }
