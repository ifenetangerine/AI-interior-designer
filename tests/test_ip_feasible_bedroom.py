"""Toy grid IP test without LLM."""

from colayout.grid.discretize import GridSpec
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def test_two_furniture_toy_grid():
    graph = RoomSceneGraph(
        room_id="toy",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="a", category="bed", width_m=1.0, length_m=1.0),
            FurnitureItem(id="b", category="chair", width_m=0.5, length_m=0.5),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.AGAINST_WALL, furniture="a", wall="west"
            ),
        ],
    )
    grid = GridSpec(
        width_cells=6,
        length_cells=6,
        modulor_cell_m=0.5,
        width_m=3.0,
        length_m=3.0,
    )
    result = solve_room_placement(graph, grid, SolveConfig(time_limit_s=15.0))
    assert result is not None
    assert len(result.furniture) == 2
    ids = {f.id for f in result.furniture}
    assert ids == {"a", "b"}


def test_bedroom_mock_scene():
    from colayout.llm.provider import MockLLMProvider
    from colayout.pipeline.place import place_room
    from colayout.schemas.floor import RoomSpec

    room = RoomSpec(id="bed1", type="bedroom", width_m=4.0, length_m=3.5)
    result = place_room(room, MockLLMProvider(), modulor_cell_m=0.5, coarse_scale=2)
    assert result is not None
    assert len(result.furniture) >= 3
