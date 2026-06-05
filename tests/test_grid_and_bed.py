"""Finer grid discretization and bed headboard wall constraints."""

from colayout.grid.discretize import discretize_room, resolve_modulor_cell_m
from colayout.llm.baseline import load_baseline
from colayout.llm.validate import validate_and_sanitize
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import RoomSceneGraph
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def test_preferred_cell_is_25cm():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    assert resolve_modulor_cell_m(room) == 0.25
    grid = discretize_room(room)
    assert grid.modulor_cell_m == 0.25
    assert grid.width_cells == 16
    assert grid.length_cells == 14


def test_finer_grid_than_half_meter():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    fine = discretize_room(room, 0.25)
    coarse = discretize_room(room, 0.5)
    assert fine.width_cells > coarse.width_cells
    assert fine.length_cells > coarse.length_cells


def test_bed_headboard_on_west_rot1():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    data = load_baseline("bedroom")
    data["room_id"] = room.id
    data["room_type"] = room.type
    graph, _ = validate_and_sanitize(RoomSceneGraph.model_validate(data), room)
    grid = discretize_room(room)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2, time_limit_s=25)
    assert result is not None
    bed = next(f for f in result.furniture if f.category == "bed")
    assert bed.origin_i == 0
    assert bed.orientation == 1
    assert bed.width_cells >= bed.length_cells
