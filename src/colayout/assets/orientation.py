"""Placement vs Kenney mesh orientation contract.

IP solver:
  rot=0 — footprint width along room i (+x); front faces +i.
  rot=1 — footprint width along room j (+z); front faces +j.
  Bed against_wall — headboard edge on wall (_bed_headboard_against_wall).

Kenney OBJ files have no forward metadata. Prefer manual labels in
config/catalog/kenney_orientation_labels.json (front_dir); fallback to
asset_orientation yaw_deg in the catalog.
"""

from __future__ import annotations

import math
from typing import Any

from colayout.assets.label_store import get_label

# Per default model: extra yaw (degrees) added to orientation * 90
ASSET_ORIENTATION_DEFAULTS: dict[str, dict[str, float]] = {
    "bedDouble": {"0": 0.0, "1": 180.0},
    "chair": {"0": 180.0, "1": 270.0},
    "desk": {"0": 0.0, "1": 90.0},
    "loungeSofa": {"0": 0.0, "1": 180.0},
    "table": {"0": 0.0, "1": 0.0},
    "tableCoffee": {"0": 0.0, "1": 0.0},
    "cabinetTelevision": {"0": 0.0, "1": 180.0},
    "sideTable": {"0": 0.0, "1": 180.0},
    "sideTableDrawers": {"0": 0.0, "1": 180.0},
    "bookcaseClosed": {"0": 0.0, "1": 180.0},
    "loungeChair": {"0": 180.0, "1": 270.0},
    "lampRoundFloor": {"0": 0.0, "1": 0.0},
    "lampSquareTable": {"0": 0.0, "1": 0.0},
    "pottedPlant": {"0": 0.0, "1": 0.0},
}


def yaw_rest_deg_from_front_dir(front_dir: list[float]) -> float:
    """Map model-local front (XZ) to yaw so front aligns with room +X at rot=0."""
    dx, dz = float(front_dir[0]), float(front_dir[1])
    # Room +X = (1, 0) in XZ; Three.js rotation.y=0 faces +Z by default for many OBJs.
    # yaw_rest aligns mesh front_dir to +X: angle(+X) - angle(front) in XZ plane.
    return math.degrees(math.atan2(dz, dx)) - 90.0


def _yaw_offset_deg(
    catalog: dict[str, Any],
    model_id: str,
    category: str,
    orientation: int,
) -> float:
    """Extra yaw (degrees) for mesh alignment at this rot, before adding orientation*90."""
    label = get_label(model_id)
    if label and "front_dir" in label:
        return yaw_rest_deg_from_front_dir(label["front_dir"])

    ori_key = str(orientation % 2)
    asset_ori = catalog.get("asset_orientation") or {}
    entry = asset_ori.get(model_id)
    if entry and "yaw_deg" in entry:
        yaw_map = entry["yaw_deg"]
        if ori_key in yaw_map:
            return float(yaw_map[ori_key])
    defaults = ASSET_ORIENTATION_DEFAULTS.get(model_id)
    if defaults and ori_key in defaults:
        return float(defaults[ori_key])
    cat_yaw = catalog.get("category_yaw_deg") or {}
    return float(cat_yaw.get(category, 0.0))


def yaw_deg_for_placement(
    catalog: dict[str, Any],
    model_id: str,
    category: str,
    orientation: int,
) -> float:
    """Total degrees about Y for Three.js (placement rot + mesh offset)."""
    return float(orientation) * 90.0 + _yaw_offset_deg(
        catalog, model_id, category, orientation
    )


def rotation_y_rad(
    catalog: dict[str, Any],
    model_id: str,
    category: str,
    orientation: int,
) -> float:
    return math.radians(
        yaw_deg_for_placement(catalog, model_id, category, orientation)
    )
