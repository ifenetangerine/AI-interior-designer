#!/usr/bin/env python3
"""Run single-room furniture placement."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colayout.assets.matcher import match_assets
from colayout.llm.provider import get_llm_provider
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import FloorPlanInput, RoomSpec
from colayout.schemas.placement import FloorPlacementResult
from colayout.viz.render import render_room


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Place furniture in one room")
    parser.add_argument("--type", required=True, help="Room type, e.g. bedroom")
    parser.add_argument("--width", type=float, required=True, help="Width in meters")
    parser.add_argument("--length", type=float, required=True, help="Length in meters")
    parser.add_argument("--id", default="room_1")
    parser.add_argument("--preferences", default="")
    parser.add_argument(
        "--cell-m",
        type=float,
        default=0.25,
        help="Grid cell size in meters (auto-coarsens for very large rooms)",
    )
    parser.add_argument("--out", "-o", type=Path, required=True)
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument(
        "--no-save-scene-graph",
        action="store_true",
        help="Do not write scene_graph_<room_id>.json",
    )
    args = parser.parse_args()

    room = RoomSpec(
        id=args.id,
        type=args.type,
        width_m=args.width,
        length_m=args.length,
        preferences=args.preferences,
    )
    llm = get_llm_provider(use_mock=args.mock_llm)
    bundle = place_room_with_graph(room, llm, args.cell_m)
    if bundle is None:
        print("Placement failed", file=sys.stderr)
        sys.exit(1)

    placement = bundle.placement
    args.out.mkdir(parents=True, exist_ok=True)
    floor = FloorPlacementResult(modulor_cell_m=args.cell_m, rooms=[placement])
    args.out.joinpath("layout.json").write_text(
        floor.model_dump_json(indent=2), encoding="utf-8"
    )

    if not args.no_save_scene_graph:
        sg_path = args.out / f"scene_graph_{placement.room_id}.json"
        sg_path.write_text(bundle.scene_graph.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote {sg_path}")
        if bundle.layout_draft is not None:
            draft_path = args.out / f"layout_draft_{placement.room_id}.json"
            draft_path.write_text(
                bundle.layout_draft.model_dump_json(indent=2), encoding="utf-8"
            )
            print(f"Wrote {draft_path}")

    render_room(placement, args.out / f"layout_{placement.room_id}.png")
    scene = match_assets(floor)
    args.out.joinpath("scene_3d.json").write_text(
        scene.model_dump_json(indent=2), encoding="utf-8"
    )
    print(f"Done: {args.out}")


if __name__ == "__main__":
    main()
