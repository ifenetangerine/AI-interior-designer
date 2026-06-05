"""Load deterministic mock layout drafts from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from colayout.catalog.kenney_index import footprint_for_model
from colayout.llm.room_program import density_tier, room_area_m2
from colayout.schemas.floor import RoomSpec

ROOT = Path(__file__).resolve().parents[3]
LAYOUTS_PATH = ROOT / "config" / "catalog" / "mock_room_layouts.yaml"

# Reference room sizes each mock layout was authored for.
REF_ROOM_M: dict[str, tuple[float, float]] = {
    "bedroom": (4.0, 3.5),
    "living_room": (4.0, 3.5),
    "kitchen": (5.0, 4.0),
}


def _footprint_m(model_id: str, orientation: int) -> tuple[float, float]:
    w, d = footprint_for_model(model_id)
    if orientation in (1, 3):
        return d, w
    return w, d


def _scale_placements(
    placements: list[dict],
    room: RoomSpec,
) -> list[dict]:
    ref_w, ref_l = REF_ROOM_M.get(room.type, (room.width_m, room.length_m))
    if ref_w <= 0 or ref_l <= 0:
        return [dict(p) for p in placements]
    sx = room.width_m / ref_w
    sz = room.length_m / ref_l
    scaled: list[dict] = []
    for raw in placements:
        p = dict(raw)
        p["center_x_m"] = float(p["center_x_m"]) * sx
        p["center_z_m"] = float(p["center_z_m"]) * sz
        scaled.append(p)
    return scaled


def load_mock_layout(room: RoomSpec) -> dict:
    with LAYOUTS_PATH.open(encoding="utf-8") as f:
        layouts = yaml.safe_load(f)
    room_layouts = layouts.get(room.type)
    if not room_layouts:
        raise ValueError(f"No mock layouts for room type '{room.type}'")
    tier = density_tier(room_area_m2(room))
    kit = room_layouts.get(tier) or room_layouts.get("standard")
    if not kit:
        raise ValueError(f"No mock layout for {room.type} tier {tier}")
    placements = _scale_placements(list(kit.get("placements", [])), room)
    return {
        "room_type": room.type,
        "placements": placements,
        "weights": dict(kit.get("weights", {"rel": 0.2, "bal": 0.0, "walk": 0.1})),
    }
