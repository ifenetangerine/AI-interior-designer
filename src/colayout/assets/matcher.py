from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from colayout.schemas.placement import FloorPlacementResult, PlacedFurniture, RoomPlacementResult

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data" / "catalog" / "assets.json"


class Asset3DPlacement(BaseModel):
    furniture_id: str
    category: str
    asset_id: str
    position_m: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: float = 0.0
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])


class Scene3D(BaseModel):
    modulor_cell_m: float
    placements: list[Asset3DPlacement]


def _load_catalog() -> list[dict]:
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)["assets"]


def _size_error(asset: dict, placed: PlacedFurniture, orientation_swap: bool) -> float:
    pw, pl, ph = placed.width_m, placed.length_m, 0.9
    aw, ad, ah = asset["width_m"], asset["depth_m"], asset["height_m"]
    if orientation_swap:
        pw, pl = pl, pw
    return abs(aw - pw) + abs(ad - pl) + abs(ah - ph) * 0.1


def match_assets(floor_result: FloorPlacementResult) -> Scene3D:
    catalog = _load_catalog()
    placements: list[Asset3DPlacement] = []
    cell = floor_result.modulor_cell_m

    for room in floor_result.rooms:
        placements.extend(_match_room(room, catalog, cell))

    return Scene3D(modulor_cell_m=floor_result.modulor_cell_m, placements=placements)


def _match_room(
    room: RoomPlacementResult,
    catalog: list[dict],
    cell_m: float,
) -> list[Asset3DPlacement]:
    out: list[Asset3DPlacement] = []
    for f in room.furniture:
        candidates = [a for a in catalog if a["category"] == f.category]
        if not candidates:
            candidates = catalog
        swap = f.orientation in (1, 3)
        best = min(candidates, key=lambda a: _size_error(a, f, swap))
        x = (f.centroid_i + 0.5) * cell_m
        y = (f.centroid_j + 0.5) * cell_m
        rot = f.orientation * 90.0
        out.append(
            Asset3DPlacement(
                furniture_id=f"{room.room_id}:{f.id}",
                category=f.category,
                asset_id=best["id"],
                position_m=[x, y, 0.0],
                rotation_deg=rot,
                scale=[1.0, 1.0, 1.0],
            )
        )
    return out
