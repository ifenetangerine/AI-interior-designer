"""Tests for hybrid Stage 1 CP-SAT feasibility solver."""

from colayout.llm.provider import MockLLMProvider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.solver.hybrid_adapters import draft_to_hybrid_state
from colayout.solver.stage1_solver import solve_stage1_feasibility
from colayout.llm.draft_to_hints import draft_to_scene_graph


def _bedroom_state():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, _ = validate_layout_draft(draft, room)
    graph = draft_to_scene_graph(draft, room)
    return draft_to_hybrid_state(draft, room, graph)


def test_stage1_returns_feasible_non_overlapping_centers():
    state = _bedroom_state()
    positions = solve_stage1_feasibility(state)
    assert positions is not None
    free = [i for i in state.items if not i.fixed]
    assert len(positions) == len(state.items)
    for item in free:
        pos = positions[item.id]
        assert 0 <= pos.x <= state.width_m
        assert 0 <= pos.z <= state.length_m
        assert pos.theta_deg in (0.0, 90.0, 180.0, 270.0)


def test_stage1_respects_room_bounds():
    state = _bedroom_state()
    positions = solve_stage1_feasibility(state)
    assert positions is not None
    for item in state.items:
        if item.fixed:
            continue
        pos = positions[item.id]
        hw = item.dimensions.width_x / 2.0
        hd = item.dimensions.depth_z / 2.0
        if int(round(pos.theta_deg / 90.0)) % 2 == 1:
            hw, hd = hd, hw
        assert pos.x - hw >= -0.01
        assert pos.x + hw <= state.width_m + 0.01
        assert pos.z - hd >= -0.01
        assert pos.z + hd <= state.length_m + 0.01
