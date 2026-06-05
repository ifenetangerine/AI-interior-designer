#!/usr/bin/env python3
"""Build Kenney furniture catalog with bbox dimensions, roles, and room tags."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OBJ_DIR = ROOT / "kenney_furniture-kit" / "Models" / "OBJ format"
OUT_PATH = ROOT / "data" / "catalog" / "kenney_catalog.json"
TAXONOMY_PATH = ROOT / "config" / "catalog" / "kenney_taxonomy.yaml"

CATEGORY_DEFAULTS: dict[str, str] = {
    "bed": "bedDouble",
    "chair": "chair",
    "desk": "desk",
    "sofa": "loungeSofa",
    "wardrobe": "cabinetBed",
    "tv_stand": "cabinetTelevision",
    "coffee_table": "tableCoffee",
    "counter": "kitchenCabinet",
    "fridge": "kitchenFridge",
    "dining_table": "table",
    "nightstand": "sideTable",
    "dresser": "cabinetBedDrawer",
    "bookshelf": "bookcaseClosed",
}

VERTEX_RE = re.compile(r"^v\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)")

KITCHEN_ORIENTATION = {
    "kitchenBar": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenBarEnd": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenCabinet": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenCabinetDrawer": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenStove": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenStoveElectric": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenSink": {"yaw_deg": {"0": 0, "1": 90}},
    "kitchenFridge": {"yaw_deg": {"0": 0, "1": 0}},
    "kitchenFridgeLarge": {"yaw_deg": {"0": 0, "1": 0}},
    "kitchenFridgeSmall": {"yaw_deg": {"0": 0, "1": 0}},
}


def _bbox_from_obj(path: Path) -> tuple[float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    with path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = VERTEX_RE.match(line.strip())
            if m:
                xs.append(float(m.group(1)))
                ys.append(float(m.group(2)))
                zs.append(float(m.group(3)))
    if not xs:
        return 1.0, 1.0, 1.0
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    depth = max(zs) - min(zs)
    return round(width, 3), round(depth, 3), round(height, 3)


def _load_taxonomy() -> dict:
    with TAXONOMY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _is_excluded(model_id: str, taxonomy: dict) -> bool:
    for prefix in taxonomy.get("exclude_prefixes", []):
        if model_id.startswith(prefix):
            return True
    return False


def _resolve_role_rooms(model_id: str, taxonomy: dict) -> tuple[str, list[str]]:
    overrides = taxonomy.get("overrides") or {}
    if model_id in overrides:
        o = overrides[model_id]
        return o["role"], list(o.get("rooms", []))

    prefix_rules = taxonomy.get("prefix_rules") or []
    matched: tuple[str, list[str]] | None = None
    best_len = -1
    for rule in prefix_rules:
        prefix = rule["prefix"]
        if model_id.startswith(prefix) and len(prefix) > best_len:
            best_len = len(prefix)
            matched = (rule["role"], list(rule.get("rooms", [])))

    if matched:
        return matched

    default = taxonomy.get("default") or {}
    return default.get("role", "decor"), list(default.get("rooms", []))


def main() -> None:
    if not OBJ_DIR.is_dir():
        raise SystemExit(f"OBJ directory not found: {OBJ_DIR}")

    taxonomy = _load_taxonomy()
    role_to_category: dict[str, str] = taxonomy.get("role_to_category") or {}

    model_ids = {p.stem for p in OBJ_DIR.glob("*.obj")}
    assets: list[dict] = []
    for model_id in sorted(model_ids):
        if _is_excluded(model_id, taxonomy):
            continue
        obj_path = OBJ_DIR / f"{model_id}.obj"
        mtl_path = OBJ_DIR / f"{model_id}.mtl"
        w, d, h = _bbox_from_obj(obj_path)
        rel_obj = obj_path.relative_to(ROOT).as_posix()
        rel_mtl = mtl_path.relative_to(ROOT).as_posix() if mtl_path.exists() else None
        role, rooms = _resolve_role_rooms(model_id, taxonomy)
        category = role_to_category.get(role, "misc")
        assets.append(
            {
                "id": model_id,
                "role": role,
                "rooms": rooms,
                "category": category,
                "obj": rel_obj,
                "mtl": rel_mtl,
                "width_m": w,
                "depth_m": d,
                "height_m": h,
                "default_scale": 1.0,
            }
        )

    CATEGORY_YAW_DEG: dict[str, float] = {
        "chair": 180.0,
        "desk": 0.0,
        "sofa": 0.0,
        "bed": 0.0,
        "dining_table": 0.0,
        "coffee_table": 0.0,
        "counter": 0.0,
        "fridge": 0.0,
    }

    ASSET_ORIENTATION: dict[str, dict] = {
        "bedDouble": {"yaw_deg": {"0": 0, "1": 180}},
        "chair": {"yaw_deg": {"0": 180, "1": 270}},
        "desk": {"yaw_deg": {"0": 0, "1": 90}},
        "loungeSofa": {"yaw_deg": {"0": 0, "1": 180}},
        "table": {"yaw_deg": {"0": 0, "1": 0}},
        "tableCoffee": {"yaw_deg": {"0": 0, "1": 0}},
        "cabinetTelevision": {"yaw_deg": {"0": 0, "1": 180}},
        "sideTable": {"yaw_deg": {"0": 0, "1": 180}},
        "sideTableDrawers": {"yaw_deg": {"0": 0, "1": 180}},
        "bookcaseClosed": {"yaw_deg": {"0": 0, "1": 180}},
        "loungeChair": {"yaw_deg": {"0": 180, "1": 270}},
        "lampRoundFloor": {"yaw_deg": {"0": 0, "1": 0}},
        "lampSquareTable": {"yaw_deg": {"0": 0, "1": 0}},
        "pottedPlant": {"yaw_deg": {"0": 0, "1": 0}},
        **KITCHEN_ORIENTATION,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "category_defaults": CATEGORY_DEFAULTS,
        "category_yaw_deg": CATEGORY_YAW_DEG,
        "asset_orientation": ASSET_ORIENTATION,
        "role_to_category": role_to_category,
        "assets": assets,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(assets)} placeable assets to {OUT_PATH}")


if __name__ == "__main__":
    main()
