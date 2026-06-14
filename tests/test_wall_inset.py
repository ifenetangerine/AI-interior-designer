"""Soft against_wall penalties on kitchen counter runs."""

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def test_kitchen_counter_chain_solves_with_soft_wall_relations():
    room = RoomSpec(id="k1", type="kitchen", width_m=5.0, length_m=4.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room, refine_mode=False)
    grid = discretize_room(room, 0.25)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2)
    assert result is not None

    chains = [
        c
        for c in graph.constraints
        if c.type == ConstraintType.ADJACENT_CHAIN
    ]
    assert chains
    chain_ids = set(chains[0].furniture_ids)
    placed = {f.id for f in result.furniture}
    assert chain_ids & placed
