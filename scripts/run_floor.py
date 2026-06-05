#!/usr/bin/env python3
"""Run multi-room furniture placement pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colayout.assets.matcher import match_assets
from colayout.llm.provider import get_llm_provider
from colayout.pipeline.place import place_floor_with_graphs
from colayout.schemas.floor import FloorPlanInput
from colayout.viz.render import render_room


def _save_scene_graphs(out_dir: Path, scene_graphs: dict) -> None:
    for room_id, graph in scene_graphs.items():
        path = out_dir / f"scene_graph_{room_id}.json"
        path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote {path}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Place furniture for all rooms in a floor JSON")
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--out", "-o", type=Path, required=True)
    parser.add_argument("--mock-llm", action="store_true", help="Use static baseline templates (no API)")
    parser.add_argument(
        "--no-save-scene-graph",
        action="store_true",
        help="Do not write scene_graph_<room_id>.json files",
    )
    args = parser.parse_args()

    floor = FloorPlanInput.model_validate_json(args.input.read_text(encoding="utf-8"))
    llm = get_llm_provider(use_mock=args.mock_llm)

    bundle = place_floor_with_graphs(floor, llm)
    result = bundle.floor
    args.out.mkdir(parents=True, exist_ok=True)

    layout_path = args.out / "layout.json"
    layout_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    if not args.no_save_scene_graph:
        _save_scene_graphs(args.out, bundle.scene_graphs)
        for room_id, draft in bundle.layout_drafts.items():
            path = args.out / f"layout_draft_{room_id}.json"
            path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
            print(f"Wrote {path}")

    for room in result.rooms:
        render_room(room, args.out / f"layout_{room.room_id}.png")

    scene = match_assets(result)
    scene_path = args.out / "scene_3d.json"
    scene_path.write_text(scene.model_dump_json(indent=2), encoding="utf-8")

    print(f"Wrote {layout_path}")
    print(f"Wrote {scene_path}")
    for room in result.rooms:
        print(f"  - layout_{room.room_id}.png")


if __name__ == "__main__":
    main()
