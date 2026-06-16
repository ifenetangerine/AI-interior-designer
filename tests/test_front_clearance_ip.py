"""Front-clearance hard constraints in CP-SAT."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.grid.discretize import discretize_room
from colayout.ip.constraints import add_hard_constraints
from colayout.ip.front_clearance import add_front_clearance_constraints
from colayout.ip.solver import _build_furniture_vars
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def _solve_fixed(
    graph: RoomSceneGraph,
    positions: dict[str, tuple[int, int, int]],
    *,
    width_m: float = 4.0,
    length_m: float = 3.5,
) -> bool:
    grid = discretize_room(
        RoomSpec(id="t", type=graph.room_type, width_m=width_m, length_m=length_m),
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
    add_front_clearance_constraints(model, fv_list, graph, grid.modulor_cell_m)
    for fv in fv_list:
        ox, oy, rot = positions[fv.item_id]
        model.Add(fv.ox == ox)
        model.Add(fv.oy == oy)
        model.Add(fv.rot == rot)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_dresser_rejects_blocker_in_front():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="bedroom",
        furniture=[
            FurnitureItem(
                id="dresser",
                model_id="cabinetBed",
                category="dresser",
                width_m=1.0,
                length_m=0.5,
            ),
            FurnitureItem(
                id="blocker",
                model_id="bookcaseClosed",
                category="bookshelf",
                width_m=0.5,
                length_m=0.4,
            ),
        ],
        constraints=[],
    )
    assert not _solve_fixed(
        graph, {"dresser": (0, 4, 0), "blocker": (4, 4, 0)}
    )
    assert _solve_fixed(graph, {"dresser": (0, 4, 0), "blocker": (4, 0, 0)})


def test_desk_allows_chair_in_front():
    graph = RoomSceneGraph(
        room_id="t",
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
    assert _solve_fixed(graph, {"desk": (0, 4, 0), "chair": (4, 4, 0)})


def test_tv_stand_allows_sofa_in_front():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="living_room",
        furniture=[
            FurnitureItem(
                id="tv",
                model_id="cabinetTelevision",
                category="tv_stand",
                width_m=0.8,
                length_m=0.25,
            ),
            FurnitureItem(
                id="sofa",
                model_id="loungeSofa",
                category="sofa",
                width_m=1.5,
                length_m=0.8,
            ),
        ],
        constraints=[],
    )
    assert _solve_fixed(graph, {"tv": (0, 4, 0), "sofa": (4, 2, 0)})


def test_counter_rejects_chair_in_front_on_north_wall():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="kitchen",
        furniture=[
            FurnitureItem(
                id="counter",
                model_id="kitchenCabinet",
                category="counter",
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
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.AGAINST_WALL,
                furniture="counter",
                wall="north",
            )
        ],
    )
    assert not _solve_fixed(
        graph,
        {"counter": (10, 14, 0), "chair": (10, 11, 0)},
        width_m=5.0,
        length_m=4.0,
    )


def test_mock_kitchen_no_chair_blocks_counter_front():
    from colayout.llm.provider import MockLLMProvider
    from colayout.pipeline.place import place_room_with_graph
    from colayout.placement.category_constraints import front_clearance_m
    from colayout.schemas.scene import ConstraintType

    room = RoomSpec(id="k1", type="kitchen", width_m=5.0, length_m=4.0)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), modulor_cell_m=0.25, placement_mode="llm_refine"
    )
    assert bundle is not None
    cell = bundle.placement.modulor_cell_m
    clearance_cells = int(round((front_clearance_m("counter") or 0) / cell))
    wall_by = {
        c.furniture: c.wall
        for c in bundle.scene_graph.constraints
        if c.type == ConstraintType.AGAINST_WALL
    }
    counters = [f for f in bundle.placement.furniture if f.category == "counter"]
    chairs = [f for f in bundle.placement.furniture if f.category == "chair"]
    for counter in counters:
        wall = wall_by.get(counter.id)
        if wall != "north":
            continue
        zj0, zj1 = counter.origin_j - clearance_cells, counter.origin_j
        zi0, zi1 = counter.origin_i, counter.origin_i + counter.width_cells
        for chair in chairs:
            ci0, ci1 = chair.origin_i, chair.origin_i + chair.width_cells
            cj0, cj1 = chair.origin_j, chair.origin_j + chair.length_cells
            overlap = not (ci1 <= zi0 or ci0 >= zi1 or cj1 <= zj0 or cj0 >= zj1)
            assert not overlap, f"{chair.id} blocks {counter.id} front clearance"


def test_counter_rejects_wardrobe_in_front():
    graph = RoomSceneGraph(
        room_id="t",
        room_type="kitchen",
        furniture=[
            FurnitureItem(
                id="counter",
                model_id="kitchenCounter",
                category="counter",
                width_m=1.0,
                length_m=0.6,
            ),
            FurnitureItem(
                id="wardrobe",
                model_id="cabinetBed",
                category="wardrobe",
                width_m=1.0,
                length_m=0.5,
            ),
        ],
        constraints=[],
    )
    assert not _solve_fixed(
        graph, {"counter": (0, 4, 0), "wardrobe": (4, 4, 0)}
    )
