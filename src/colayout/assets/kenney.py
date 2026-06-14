"""Match placement results to Kenney OBJ assets."""

from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel, Field

from colayout.assets.label_store import get_wall_anchor
from colayout.assets.orientation import rotation_y_rad
from colayout.catalog.kenney_index import height_for_model, role_for_model
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data" / "catalog" / "kenney_catalog.json"

RUG_Y_OFFSET_M = 0.005  # lift rugs off the floor plane to avoid z-fighting


BACK_WALL_CATEGORIES = frozenset(
    {"counter", "fridge", "wardrobe", "tv_stand", "dresser"}
)


class KenneyPlacement(BaseModel):
    furniture_id: str
    category: str
    model_id: str
    obj_url: str
    mtl_url: str | None = None
    position_m: list[float] = Field(min_length=3, max_length=3)
    rotation_y_rad: float = 0.0
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    footprint_m: list[float] = Field(
        min_length=4,
        max_length=4,
        description="Axis-aligned footprint [x0, z0, x1, z1] in room meters",
    )
    wall_anchor: str | None = Field(
        default=None,
        description="center | back_center — viewer snaps mesh back to wall edge",
    )


def footprint_from_placed(f: PlacedFurniture, cell_m: float) -> tuple[float, float, float, float]:
    """Grid-cell footprint (ceil-rounded; used by IP solver occupancy)."""
    x0 = f.origin_i * cell_m
    z0 = f.origin_j * cell_m
    x1 = (f.origin_i + f.width_cells) * cell_m
    z1 = (f.origin_j + f.length_cells) * cell_m
    return x0, z0, x1, z1


def tight_footprint_from_placed(
    f: PlacedFurniture, cell_m: float
) -> tuple[float, float, float, float]:
    """Catalog-sized footprint for viewer/mesh alignment (no grid ceil inflation)."""
    swap = f.orientation in (1, 3)
    ext_x = f.length_m if swap else f.width_m
    ext_z = f.width_m if swap else f.length_m
    cx = f.centroid_i * cell_m
    cz = f.centroid_j * cell_m
    return (cx - ext_x / 2, cz - ext_z / 2, cx + ext_x / 2, cz + ext_z / 2)


def center_from_footprint(x0: float, z0: float, x1: float, z1: float) -> tuple[float, float]:
    return (x0 + x1) / 2.0, (z0 + z1) / 2.0


def load_kenney_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _assets_by_id(catalog: dict) -> dict[str, dict]:
    return {a["id"]: a for a in catalog.get("assets", [])}


def _assets_by_category(catalog: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for a in catalog.get("assets", []):
        out.setdefault(a["category"], []).append(a)
    return out


def _pick_model(
    placed: PlacedFurniture,
    catalog: dict,
    by_id: dict[str, dict],
    by_cat: dict[str, list[dict]],
) -> dict:
    if placed.model_id and placed.model_id in by_id:
        return by_id[placed.model_id]
    defaults = catalog.get("category_defaults", {})
    default_id = defaults.get(placed.category)
    if default_id and default_id in by_id:
        return by_id[default_id]
    candidates = by_cat.get(placed.category, [])
    if not candidates:
        candidates = catalog.get("assets", [])
    swap = placed.orientation in (1, 3)
    pw, pd = placed.width_m, placed.length_m
    if swap:
        pw, pd = pd, pw

    def err(a: dict) -> float:
        return abs(a["width_m"] - pw) + abs(a["depth_m"] - pd)

    return min(candidates, key=err)


def _scale_for_fit(placed: PlacedFurniture, asset: dict) -> list[float]:
    swap = placed.orientation in (1, 3)
    pw, pd = placed.width_m, placed.length_m
    if swap:
        pw, pd = pd, pw
    aw = max(asset["width_m"], 0.01)
    ad = max(asset["depth_m"], 0.01)
    sx = pw / aw
    sz = pd / ad
    s = min(sx, sz, 2.5)
    return [s, s, s]


def match_kenney_assets(
    placement: RoomPlacementResult,
    catalog: dict | None = None,
    url_prefix: str = "/kenney",
) -> list[KenneyPlacement]:
    catalog = catalog or load_kenney_catalog()
    by_id = _assets_by_id(catalog)
    by_cat = _assets_by_category(catalog)
    cell = placement.modulor_cell_m
    by_fid = {f.id: f for f in placement.furniture}
    out: list[KenneyPlacement] = []

    for f in placement.furniture:
        asset = _pick_model(f, catalog, by_id, by_cat)
        obj_name = Path(asset["obj"]).name
        mtl_url = None
        if asset.get("mtl"):
            mtl_url = f"{url_prefix}/{Path(asset['mtl']).name}"

        x0, z0, x1, z1 = tight_footprint_from_placed(f, cell)
        cx, cz = center_from_footprint(x0, z0, x1, z1)
        rot_y = rotation_y_rad(
            catalog, asset["id"], f.category, f.orientation
        )
        scale = _scale_for_fit(f, asset)
        wall_anchor = get_wall_anchor(asset["id"], f.category)

        surface_y = 0.0
        if f.stack_parent_id and f.stack_mode == "on_top":
            parent = by_fid.get(f.stack_parent_id)
            if parent:
                parent_asset = _pick_model(parent, catalog, by_id, by_cat)
                # Parent meshes are scaled to fit their footprint; the surface
                # height scales with them.
                parent_scale = _scale_for_fit(parent, parent_asset)
                surface_y = (
                    height_for_model(parent_asset["id"], catalog)
                    * parent_scale[1]
                )
        elif f.stack_mode == "under" or role_for_model(asset["id"]) == "rug":
            # Lift rugs slightly off the floor plane to avoid z-fighting.
            surface_y = RUG_Y_OFFSET_M

        out.append(
            KenneyPlacement(
                furniture_id=f"{placement.room_id}:{f.id}",
                category=f.category,
                model_id=asset["id"],
                obj_url=f"{url_prefix}/{obj_name}",
                mtl_url=mtl_url,
                position_m=[cx, surface_y, cz],
                rotation_y_rad=rot_y,
                scale=scale,
                footprint_m=[x0, z0, x1, z1],
                wall_anchor=wall_anchor,
            )
        )
    return out
