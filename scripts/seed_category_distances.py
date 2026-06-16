#!/usr/bin/env python3
"""Report median category-pair distances from golden layouts (for tuning YAML)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from colayout.catalog.kenney_index import placement_category

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "data" / "golden_layouts"


def _dist(a: dict, b: dict) -> float:
    return abs(a["x"] - b["x"]) + abs(a["z"] - b["z"])


def main() -> None:
    pairs: dict[tuple[str, str], list[float]] = defaultdict(list)
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        if path.name == ".gitkeep":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        draft = data.get("draft") or data
        placements = draft.get("placements") or []
        points = [
            {
                "cat": placement_category(p["model_id"]),
                "x": p["center_x_m"],
                "z": p["center_z_m"],
            }
            for p in placements
        ]
        for i, a in enumerate(points):
            for b in points[i + 1 :]:
                key = tuple(sorted((a["cat"], b["cat"])))
                pairs[key].append(_dist(a, b))

    for key in sorted(pairs):
        vals = sorted(pairs[key])
        mid = vals[len(vals) // 2]
        print(f"{key[0]} <-> {key[1]}: n={len(vals)} median={mid:.2f}m")

    print(f"\nAnalyzed {len(list(GOLDEN_DIR.glob('*.json')))} golden layout files")


if __name__ == "__main__":
    main()
