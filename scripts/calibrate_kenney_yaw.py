#!/usr/bin/env python3
"""Print Kenney default model bboxes to help calibrate asset_orientation yaw."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colayout.assets.orientation import ASSET_ORIENTATION_DEFAULTS
from scripts.build_kenney_catalog import CATEGORY_DEFAULTS, _bbox_from_obj

OBJ_DIR = ROOT / "kenney_furniture-kit" / "Models" / "OBJ format"


def main() -> None:
    print("Default models (category -> id):")
    for cat, mid in sorted(CATEGORY_DEFAULTS.items()):
        obj = OBJ_DIR / f"{mid}.obj"
        if not obj.exists():
            print(f"  {cat}: {mid} MISSING")
            continue
        w, d, h = _bbox_from_obj(obj)
        yaw = ASSET_ORIENTATION_DEFAULTS.get(mid, {})
        print(f"  {cat}: {mid}  bbox w={w} d={d} h={h}  yaw={yaw}")
    catalog = ROOT / "data" / "catalog" / "kenney_catalog.json"
    if catalog.exists():
        data = json.loads(catalog.read_text())
        print("\nasset_orientation in catalog:")
        print(json.dumps(data.get("asset_orientation", {}), indent=2))


if __name__ == "__main__":
    main()
