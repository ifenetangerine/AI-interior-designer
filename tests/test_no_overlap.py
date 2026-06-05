"""Overlap and bounds checks."""

import json
from pathlib import Path

from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_floor
from colayout.schemas.floor import FloorPlanInput


def _assert_no_overlap(room) -> None:
    w, l = room.grid_w, room.grid_l
    for i in range(w):
        for j in range(l):
            occupants = []
            for f in room.furniture:
                if f.stack_parent_id:
                    continue
                if (
                    f.origin_i <= i < f.origin_i + f.width_cells
                    and f.origin_j <= j < f.origin_j + f.length_cells
                ):
                    occupants.append(f.id)
            if len(occupants) > 1:
                raise AssertionError(
                    f"Overlap at ({i},{j}): {occupants} in room {room.room_id}"
                )


def _assert_in_bounds(room) -> None:
    for f in room.furniture:
        assert f.origin_i >= 0
        assert f.origin_j >= 0
        assert f.origin_i + f.width_cells <= room.grid_w
        assert f.origin_j + f.length_cells <= room.grid_l


def test_studio_floor_no_overlap():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "examples" / "studio.json").read_text())
    floor = FloorPlanInput.model_validate(data)
    result = place_floor(floor, MockLLMProvider(), max_workers=2)
    assert len(result.rooms) == 2
    for room in result.rooms:
        _assert_no_overlap(room)
        _assert_in_bounds(room)


def test_scene_3d_has_assets():
    from colayout.assets.matcher import match_assets

    root = Path(__file__).resolve().parents[1]
    floor = FloorPlanInput.model_validate_json(
        (root / "examples" / "studio.json").read_text()
    )
    layout = place_floor(floor, MockLLMProvider())
    scene = match_assets(layout)
    assert len(scene.placements) >= 7
    for p in scene.placements:
        assert p.asset_id
