"""IP placement from a custom dynamic scene graph fixture."""

import json
from pathlib import Path

from colayout.grid.discretize import discretize_room
from colayout.ip.solver import solve_room_placement
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import RoomSceneGraph
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def test_custom_four_piece_bedroom():
    root = Path(__file__).resolve().parents[1]
    data = json.loads(
        (root / "tests" / "fixtures" / "scene_graph_custom.json").read_text()
    )
    graph = RoomSceneGraph.model_validate(data)
    room = RoomSpec(id="bed_custom", type="bedroom", width_m=4.0, length_m=3.5)
    grid = discretize_room(room, 0.5)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2)
    assert result is not None
    assert len(result.furniture) == 4
