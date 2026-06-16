"""Tests for hybrid Stage 2 continuous aesthetic refiner."""

import math

from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.solver.hybrid_adapters import draft_to_hybrid_state
from colayout.solver.hybrid_types import FurniturePosition, HybridSolveConfig
from colayout.solver.stage1_solver import solve_stage1_feasibility
from colayout.solver.stage2_costs import overlap_cost, sightline_cost
from colayout.solver.stage2_refiner import refine_stage2_aesthetic


def _living_room_state():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, _ = validate_layout_draft(draft, room)
    graph = draft_to_scene_graph(draft, room)
    return draft_to_hybrid_state(draft, room, graph)


def test_stage2_reduces_overlap_energy():
    state = _living_room_state()
    stage1 = solve_stage1_feasibility(state)
    assert stage1 is not None
    free = [i for i in state.items if not i.fixed]
    before = overlap_cost(free, stage1)
    refined = refine_stage2_aesthetic(state, stage1, HybridSolveConfig())
    after = overlap_cost(free, refined)
    assert after <= before + 0.15


def test_stage2_improves_sofa_tv_sightline():
    state = _living_room_state()
    stage1 = solve_stage1_feasibility(state)
    assert stage1 is not None
    free = [i for i in state.items if not i.fixed]
    before = sightline_cost(free, stage1)
    refined = refine_stage2_aesthetic(
        state,
        stage1,
        HybridSolveConfig(w_overlap=1.0, w_sightline=20.0, w_wall=1.0),
    )
    after = sightline_cost(free, refined)
    assert after <= before + 0.05


def _angular_distance_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def test_stage2_stays_within_wander_bounds():
    state = _living_room_state()
    stage1 = solve_stage1_feasibility(state)
    assert stage1 is not None
    config = HybridSolveConfig(wander_margin_m=0.3, theta_wander_deg=30.0)
    refined = refine_stage2_aesthetic(state, stage1, config)
    for item in state.items:
        if item.fixed:
            continue
        s1 = stage1[item.id]
        r = refined[item.id]
        assert abs(r.x - s1.x) <= config.wander_margin_m + 0.02
        assert abs(r.z - s1.z) <= config.wander_margin_m + 0.02
        assert _angular_distance_deg(r.theta_deg, s1.theta_deg) <= config.theta_wander_deg + 2.0
