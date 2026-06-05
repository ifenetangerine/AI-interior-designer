"""Kitchen counter adjacent_chain feasibility."""

from colayout.grid.discretize import discretize_room
from colayout.llm.mock_kits import load_mock_kit
from colayout.llm.validate import validate_and_sanitize
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType, RoomSceneGraph
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def test_kitchen_compact_chain_feasible():
    room = RoomSpec(id="k1", type="kitchen", width_m=4.0, length_m=3.0)
    data = load_mock_kit(room)
    data["room_id"] = room.id
    data["room_type"] = room.type
    graph = RoomSceneGraph.model_validate(data)
    graph, _ = validate_and_sanitize(graph, room)
    chains = [
        c for c in graph.constraints if c.type == ConstraintType.ADJACENT_CHAIN
    ]
    assert len(chains) >= 1
    assert len(chains[0].furniture_ids) >= 2

    grid = discretize_room(room)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2)
    assert result is not None
    assert len(result.furniture) == len(graph.furniture)
