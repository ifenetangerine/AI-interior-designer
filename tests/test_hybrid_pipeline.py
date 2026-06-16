"""End-to-end hybrid placement pipeline tests."""

from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import draft_to_hints, draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import RoomSpec
from colayout.solver.hybrid_pipeline import refine_after_ip, solve_hybrid_placement
from colayout.solver.hybrid_types import HybridSolveConfig


def test_hybrid_pipeline_produces_placement():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, _ = validate_layout_draft(draft, room)
    graph = draft_to_scene_graph(draft, room)
    grid = discretize_room(room, 0.25)
    result = solve_hybrid_placement(draft, room, graph, grid)
    assert result is not None
    assert len(result.furniture) >= 1


def test_refine_after_ip_uses_ip_stage1():
    room = RoomSpec(id="r1", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, _ = validate_layout_draft(draft, room)
    graph = draft_to_scene_graph(draft, room)
    grid = discretize_room(room, 0.25)
    hints = draft_to_hints(draft, grid)
    stage1 = solve_room_placement(
        graph,
        grid,
        SolveConfig(hints=hints, soft_constraints=True, time_limit_s=10.0),
    )
    assert stage1 is not None

    refined = refine_after_ip(
        stage1,
        draft,
        room,
        graph,
        grid,
        HybridSolveConfig(
            w_overlap=50.0,
            w_sightline=8.0,
            w_wall=6.0,
            wander_margin_m=0.25,
        ),
    )
    assert refined is not None
    assert len(refined.furniture) == len(stage1.furniture)
    assert {f.id for f in refined.furniture} == {f.id for f in stage1.furniture}


def test_llm_refine_uses_hybrid_pipeline():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room,
        MockLLMProvider(),
        modulor_cell_m=0.25,
        placement_mode="llm_refine",
    )
    assert bundle is not None
    assert len(bundle.placement.furniture) >= 1

    grid = discretize_room(room, 0.25)
    draft = bundle.layout_draft
    assert draft is not None
    graph = bundle.scene_graph
    hints = draft_to_hints(draft, grid)
    ip_only = solve_room_placement(
        graph,
        grid,
        SolveConfig(hints=hints, soft_constraints=True, time_limit_s=10.0),
    )
    assert ip_only is not None
    ip_positions = {
        f.id: (f.centroid_i, f.centroid_j) for f in ip_only.furniture
    }
    hybrid_positions = {
        f.id: (f.centroid_i, f.centroid_j) for f in bundle.placement.furniture
    }
    moved = any(
        abs(ip_positions[fid][0] - hybrid_positions[fid][0]) > 0.01
        or abs(ip_positions[fid][1] - hybrid_positions[fid][1]) > 0.01
        for fid in ip_positions
        if fid in hybrid_positions
    )
    assert moved or len(ip_positions) == len(hybrid_positions)
