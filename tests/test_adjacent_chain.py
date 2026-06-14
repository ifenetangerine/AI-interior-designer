"""Kitchen counter adjacent_chain feasibility (config-driven draft pipeline)."""

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def test_kitchen_compact_chain_feasible():
    room = RoomSpec(id="k1", type="kitchen", width_m=4.0, length_m=3.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room, refine_mode=False)
    chains = [
        c for c in graph.constraints if c.type == ConstraintType.ADJACENT_CHAIN
    ]
    assert len(chains) >= 1
    assert len(chains[0].furniture_ids) >= 2

    grid = discretize_room(room)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2)
    assert result is not None
    assert len(result.furniture) == len(graph.furniture)
