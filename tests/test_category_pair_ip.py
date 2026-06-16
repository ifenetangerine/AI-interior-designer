"""CP-SAT category-pair distance constraints from category_constraints.yaml."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.grid.discretize import discretize_room
from colayout.ip.category_distance import (
    add_category_pair_hard_constraints,
    add_category_pair_soft_penalties,
)
from colayout.ip.constraints import add_hard_constraints
from colayout.ip.solver import SolveConfig, _build_furniture_vars, solve_room_placement
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import FurnitureItem, RoomSceneGraph


def _desk_chair_graph() -> RoomSceneGraph:
    return RoomSceneGraph(
        room_id="office",
        room_type="bedroom",
        furniture=[
            FurnitureItem(
                id="desk",
                model_id="desk",
                category="desk",
                width_m=1.0,
                length_m=0.6,
            ),
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


def _solve_fixed_with_pair_hard(
    graph: RoomSceneGraph,
    positions: dict[str, tuple[int, int, int]],
) -> bool:
    grid = discretize_room(
        RoomSpec(id="t", type=graph.room_type, width_m=4.0, length_m=3.5),
        0.25,
    )
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
    add_category_pair_hard_constraints(
        model,
        fv_list,
        graph,
        grid.modulor_cell_m,
        room_width_m=grid.width_m,
        room_length_m=grid.length_m,
    )
    for fv in fv_list:
        ox, oy, rot = positions[fv.item_id]
        model.Add(fv.ox == ox)
        model.Add(fv.oy == oy)
        model.Add(fv.rot == rot)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_desk_chair_hard_rejects_too_close():
    graph = _desk_chair_graph()
    # Colocated centroids — L1 distance 0, below YAML min 0.25 m
    assert not _solve_fixed_with_pair_hard(graph, {"desk": (0, 4, 0), "chair": (0, 4, 0)})


def test_desk_chair_hard_accepts_valid_spacing():
    graph = _desk_chair_graph()
    # Chair ~0.5 m east of desk (2 cells at 0.25 m)
    assert _solve_fixed_with_pair_hard(graph, {"desk": (0, 4, 0), "chair": (4, 4, 0)})


def test_desk_chair_hard_rejects_too_far():
    graph = _desk_chair_graph()
    # Chair ~2.5 m away — above YAML max 1.25 m
    assert not _solve_fixed_with_pair_hard(
        graph, {"desk": (0, 4, 0), "chair": (10, 4, 0)}
    )


def test_soft_pair_penalties_nudge_toward_band():
    graph = _desk_chair_graph()
    grid = discretize_room(
        RoomSpec(id="t", type="bedroom", width_m=4.0, length_m=3.5),
        0.25,
    )
    result = solve_room_placement(
        graph,
        grid,
        SolveConfig(
            hints={"desk": (0, 4, 0), "chair": (0, 4, 0)},
            soft_constraints=True,
            time_limit_s=10.0,
        ),
    )
    assert result is not None
    by_id = {f.id: f for f in result.furniture}
    desk = by_id["desk"]
    chair = by_id["chair"]
    l1 = abs(desk.centroid_i - chair.centroid_i) + abs(
        desk.centroid_j - chair.centroid_j
    )
    assert l1 >= 0.25 - 0.01
