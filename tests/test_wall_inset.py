"""Wall inset keeps non-bed furniture off room boundaries."""

from colayout.grid.discretize import discretize_room
from colayout.ip.constraints import WALL_INSET_CELLS
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine
from colayout.llm.mock_kits import load_mock_kit
from colayout.llm.validate import validate_and_sanitize
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType, RoomSceneGraph


def test_kitchen_north_wall_chain_inset():
    room = RoomSpec(id="k1", type="kitchen", width_m=5.0, length_m=4.0)
    data = load_mock_kit(room)
    data["room_id"] = room.id
    graph = RoomSceneGraph.model_validate(data)
    graph, _ = validate_and_sanitize(graph, room)
    grid = discretize_room(room, 0.25)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2)
    assert result is not None

    chains = [
        c
        for c in graph.constraints
        if c.type == ConstraintType.ADJACENT_CHAIN and c.wall == "north"
    ]
    assert chains, "expected north adjacent_chain on kitchen mock"
    chain_ids = set(chains[0].furniture_ids)
    inset = WALL_INSET_CELLS
    l_grid = grid.length_cells

    for f in result.furniture:
        if f.id not in chain_ids:
            continue
        assert f.origin_j + f.length_cells <= l_grid - inset
