"""Hierarchical blueprint registry and expansion tests."""

from __future__ import annotations

import math

from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import draft_to_hints, draft_to_scene_graph
from colayout.llm.mock_blueprints import load_mock_blueprint
from colayout.placement.blueprint_expand import expand_room_blueprint
from colayout.placement.blueprint_registry import get_blueprint
from colayout.schemas.floor import RoomSpec


def test_symmetric_lounge_offsets_are_symmetric():
    bp = get_blueprint("symmetric_lounge")
    by_id = {s.slot_id: s for s in bp.slots}
    assert math.isclose(by_id["chair_l"].center_x_m, -by_id["chair_r"].center_x_m)
    assert by_id["coffee_table"].center_x_m == 0.0
    assert by_id["sofa"].center_z_m > by_id["coffee_table"].center_z_m


def test_bedside_cluster_nightstand_symmetry():
    bp = get_blueprint("bedside_cluster")
    by_id = {s.slot_id: s for s in bp.slots}
    assert math.isclose(
        by_id["nightstand_l"].center_x_m, -by_id["nightstand_r"].center_x_m
    )


def test_expand_produces_prefixed_child_ids():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    blueprint = load_mock_blueprint(room)
    expanded = expand_room_blueprint(blueprint, cell_m=0.25)
    ids = {p.id for p in expanded.draft.placements}
    assert "bed_cluster__bed" in ids
    assert "desk_cluster__desk" in ids
    assert "wardrobe" in ids
    assert len(expanded.compound_groups) == 2


def test_cluster_members_use_per_child_intervals():
    """Each child contributes its own NewIntervalVar to NoOverlap2D (not bbox only)."""
    from ortools.sat.python import cp_model

    from colayout.ip.compound_solver import build_compound_furniture_vars
    from colayout.llm.draft_to_hints import draft_to_scene_graph
    from colayout.schemas.compound import CompoundGroupPlan

    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    expanded = expand_room_blueprint(load_mock_blueprint(room), cell_m=0.25)
    lounge_plan = next(
        p for p in expanded.compound_groups if p.group_id == "lounge"
    )
    assert len(lounge_plan.members) >= 4
    grid = discretize_room(room, 0.25)
    graph = draft_to_scene_graph(
        expanded.draft, room, compound_groups=expanded.compound_groups
    )
    model = cp_model.CpModel()
    fv_list, x_iv, y_iv = build_compound_furniture_vars(model, graph, grid)
    lounge_ids = set(lounge_plan.member_ids)
    lounge_intervals = [fv.x_interval for fv in fv_list if fv.item_id in lounge_ids]
    assert len(lounge_intervals) == len(lounge_ids)


def test_compound_group_solver_keeps_lounge_rigid():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    blueprint = load_mock_blueprint(room)
    expanded = expand_room_blueprint(blueprint, cell_m=0.25)
    grid = discretize_room(room, 0.25)
    graph = draft_to_scene_graph(
        expanded.draft,
        room,
        compound_groups=expanded.compound_groups,
    )
    hints = draft_to_hints(expanded.draft, grid)
    result = solve_room_placement(
        graph,
        grid,
        SolveConfig(hints=hints, soft_constraints=True, time_limit_s=10.0),
    )
    assert result is not None
    by_id = {f.id: f for f in result.furniture}
    sofa = by_id["lounge__sofa"]
    coffee = by_id["lounge__coffee_table"]
    chair_l = by_id["lounge__chair_l"]
    chair_r = by_id["lounge__chair_r"]
    # Rigid group: cluster moves together; coffee stays centered between flank chairs.
    mid_chairs = (chair_l.centroid_i + chair_r.centroid_i) / 2
    assert math.isclose(mid_chairs, coffee.centroid_i, abs_tol=0.51)
    assert sofa.centroid_j > coffee.centroid_j
    hint_span = hints["lounge__chair_r"][0] - hints["lounge__chair_l"][0]
    assert chair_r.origin_i - chair_l.origin_i == hint_span
