"""Tests for IP hard constraints (stack, category-pair distance)."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.grid.discretize import discretize_room
from colayout.ip.category_distance import add_category_pair_hard_constraints
from colayout.ip.constraints import add_hard_constraints
from colayout.ip.solver import _build_furniture_vars
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def _solve_with_fixed_positions(
    graph: RoomSceneGraph,
    positions: dict[str, tuple[int, int, int]],
    *,
    pair_hard: bool = False,
) -> bool:
    grid = discretize_room(RoomSpec(id="t", type="bedroom", width_m=4.0, length_m=3.5), 0.25)
    model = cp_model.CpModel()
    fv_list, x_iv, y_iv = _build_furniture_vars(model, graph, grid)
    if len(x_iv) > 1:
        model.AddNoOverlap2D(x_iv, y_iv)
    add_hard_constraints(
        model,
        fv_list,
        graph.constraints,
        w_grid=grid.width_cells,
        l_grid=grid.length_cells,
    )
    if pair_hard:
        add_category_pair_hard_constraints(
            model, fv_list, graph, grid.modulor_cell_m
        )
    for fv in fv_list:
        ox, oy, rot = positions[fv.item_id]
        model.Add(fv.ox == ox)
        model.Add(fv.oy == oy)
        model.Add(fv.rot == rot)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_stack_colocation_hard():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="a", model_id="sideTable", category="nightstand", width_m=0.4, length_m=0.4),
            FurnitureItem(id="b", model_id="lampRoundTable", category="lamp_desk", width_m=0.15, length_m=0.18),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.ON_TOP_OF,
                furniture_a="b",
                furniture_b="a",
            )
        ],
    )
    assert _solve_with_fixed_positions(graph, {"a": (0, 2, 0), "b": (0, 2, 0)})
    assert not _solve_with_fixed_positions(graph, {"a": (0, 2, 0), "b": (3, 2, 0)})


def test_stack_tv_on_console_hard():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="living_room",
        furniture=[
            FurnitureItem(
                id="console",
                model_id="cabinetTelevision",
                category="bookshelf",
                width_m=0.8,
                length_m=0.25,
            ),
            FurnitureItem(
                id="tv",
                model_id="televisionModern",
                category="tv",
                width_m=0.685,
                length_m=0.128,
            ),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.ON_TOP_OF,
                furniture_a="tv",
                furniture_b="console",
            )
        ],
    )
    assert _solve_with_fixed_positions(graph, {"console": (0, 2, 0), "tv": (0, 2, 0)})
    assert not _solve_with_fixed_positions(graph, {"console": (0, 2, 0), "tv": (3, 2, 0)})


def test_non_stackable_forbids_colocation():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="a", model_id="bedDouble", category="bed", width_m=1.5, length_m=2.0),
            FurnitureItem(id="b", model_id="desk", category="desk", width_m=1.0, length_m=0.6),
        ],
        constraints=[],
    )
    assert _solve_with_fixed_positions(graph, {"a": (0, 2, 0), "b": (12, 2, 0)})
    assert not _solve_with_fixed_positions(graph, {"a": (0, 2, 0), "b": (0, 2, 0)})


def test_chair_exempt_from_wall_distance():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="kitchen",
        furniture=[
            FurnitureItem(
                id="chair",
                model_id="chair",
                category="chair",
                width_m=0.4,
                length_m=0.4,
            ),
        ],
        constraints=[],
    )
    # Center of room — fine (wall distance is not a hard constraint today)
    assert _solve_with_fixed_positions(graph, {"chair": (6, 5, 0)})
