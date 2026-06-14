"""Relational IP constraints: flank, desk-chair, dining surround."""

from colayout.grid.discretize import discretize_room
from colayout.llm.provider import MockLLMProvider
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def _bedroom_graph_with_nightstands() -> RoomSceneGraph:
    return RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="bed", category="bed", width_m=1.6, length_m=2.0),
            FurnitureItem(id="nightstand_l", category="nightstand", width_m=0.5, length_m=0.4),
            FurnitureItem(id="nightstand_r", category="nightstand", width_m=0.5, length_m=0.4),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.AGAINST_WALL, furniture="bed", wall="west"
            ),
            FurnitureConstraint(
                type=ConstraintType.FLANK,
                furniture_a="nightstand_l",
                furniture_b="bed",
                side="left",
            ),
            FurnitureConstraint(
                type=ConstraintType.FLANK,
                furniture_a="nightstand_r",
                furniture_b="bed",
                side="right",
            ),
        ],
    )


def test_nightstands_left_right_of_bed():
    graph = _bedroom_graph_with_nightstands()
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    grid = discretize_room(room)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2, time_limit_s=30)
    assert result is not None
    bed = next(f for f in result.furniture if f.id == "bed")
    left = next(f for f in result.furniture if f.id == "nightstand_l")
    right = next(f for f in result.furniture if f.id == "nightstand_r")
    assert left.centroid_j < bed.centroid_j
    assert right.centroid_j > bed.centroid_j
    assert abs((bed.centroid_j - left.centroid_j) - (right.centroid_j - bed.centroid_j)) < 0.35


def test_dining_chairs_centered_on_sides():
    graph = RoomSceneGraph(
        room_id="k1",
        room_type="kitchen",
        furniture=[
            FurnitureItem(id="table", category="dining_table", width_m=1.2, length_m=0.8),
            FurnitureItem(id="c_s", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="c_n", category="chair", width_m=0.5, length_m=0.5),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.SEATS_AROUND, furniture="table", min_seats=2
            ),
        ],
    )
    room = RoomSpec(id="k1", type="kitchen", width_m=4.0, length_m=3.5)
    result = solve_room_coarse_to_fine(
        graph, discretize_room(room), coarse_scale=2, time_limit_s=30
    )
    assert result is not None
    table = next(f for f in result.furniture if f.id == "table")
    half_ti = table.width_cells / 2
    half_tj = table.length_cells / 2
    sides: list[str] = []
    for cid in ("c_s", "c_n"):
        ch = next(f for f in result.furniture if f.id == cid)
        half_ci = ch.width_cells / 2
        half_cj = ch.length_cells / 2
        di = ch.centroid_i - table.centroid_i
        dj = ch.centroid_j - table.centroid_j
        if abs(di) <= 0.55:
            # North/south seat: centered on i, edge-touching on j.
            assert abs(abs(dj) - (half_tj + half_cj)) <= 0.5
            sides.append("north" if dj < 0 else "south")
        else:
            # East/west seat: centered on j, edge-touching on i.
            assert abs(dj) <= 0.55
            assert abs(abs(di) - (half_ti + half_ci)) <= 0.5
            sides.append("west" if di < 0 else "east")
    assert len(set(sides)) == 2


def test_two_desks_two_chairs():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="desk_a", category="desk", width_m=1.0, length_m=0.6),
            FurnitureItem(id="desk_b", category="desk", width_m=1.0, length_m=0.6),
            FurnitureItem(id="chair_a", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="chair_b", category="chair", width_m=0.5, length_m=0.5),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.IN_FRONT_OF,
                furniture_a="chair_a",
                furniture_b="desk_a",
                distance_m=0.7,
            ),
            FurnitureConstraint(
                type=ConstraintType.IN_FRONT_OF,
                furniture_a="chair_b",
                furniture_b="desk_b",
                distance_m=0.7,
            ),
        ],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=5.0, length_m=4.0)
    result = solve_room_coarse_to_fine(
        graph, discretize_room(room), coarse_scale=2, time_limit_s=30
    )
    assert result is not None
    assert len(result.furniture) == 4


def test_dining_surround():
    graph = RoomSceneGraph(
        room_id="k1",
        room_type="kitchen",
        furniture=[
            FurnitureItem(id="table", category="dining_table", width_m=1.2, length_m=0.8),
            FurnitureItem(id="c1", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="c2", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="c3", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="c4", category="chair", width_m=0.5, length_m=0.5),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.SEATS_AROUND, furniture="table", min_seats=2
            ),
        ],
    )
    room = RoomSpec(id="k1", type="kitchen", width_m=4.0, length_m=3.5)
    result = solve_room_coarse_to_fine(
        graph, discretize_room(room), coarse_scale=2, time_limit_s=35
    )
    assert result is not None
    table = next(f for f in result.furniture if f.id == "table")
    chairs = [f for f in result.furniture if f.category == "chair"]
    assert len(chairs) == 4
    ci, cj = table.centroid_i, table.centroid_j
    sides = set()
    for ch in chairs:
        if ch.centroid_j < cj - 0.2:
            sides.add("south")
        if ch.centroid_j > cj + 0.2:
            sides.add("north")
        if ch.centroid_i < ci - 0.2:
            sides.add("west")
        if ch.centroid_i > ci + 0.2:
            sides.add("east")
    assert len(sides) >= 3


def test_spacious_bedroom_has_nightstands():
    room = RoomSpec(id="s", type="bedroom", width_m=6.0, length_m=5.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    ids = {p.id for p in draft.placements}
    assert any("nightstand" in i for i in ids)
