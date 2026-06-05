"""Relational IP constraints: flank, desk-chair, dining surround."""

from colayout.grid.discretize import discretize_room
from colayout.llm.design_rules import enrich_scene_graph
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
    graph = RoomSceneGraph(
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
        ],
    )
    return enrich_scene_graph(graph)


def test_enrich_flank_constraints():
    enriched = _bedroom_graph_with_nightstands()
    flanks = [c for c in enriched.constraints if c.type == ConstraintType.FLANK]
    assert len(flanks) >= 2
    sides = {c.side for c in flanks}
    assert "left" in sides and "right" in sides


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
    assert left.origin_i <= bed.origin_i + 1
    assert right.origin_i <= bed.origin_i + 1


def test_dining_chairs_centered_on_sides():
    graph = RoomSceneGraph(
        room_id="k1",
        room_type="kitchen",
        furniture=[
            FurnitureItem(id="table", category="dining_table", width_m=1.2, length_m=0.8),
            FurnitureItem(id="c_s", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="c_n", category="chair", width_m=0.5, length_m=0.5),
        ],
        constraints=[],
    )
    graph = enrich_scene_graph(graph)
    room = RoomSpec(id="k1", type="kitchen", width_m=4.0, length_m=3.5)
    result = solve_room_coarse_to_fine(
        graph, discretize_room(room), coarse_scale=2, time_limit_s=30
    )
    assert result is not None
    table = next(f for f in result.furniture if f.id == "table")
    for cid in ("c_s", "c_n"):
        ch = next(f for f in result.furniture if f.id == cid)
        assert abs(ch.centroid_i - table.centroid_i) <= 0.5


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
        constraints=[],
    )
    graph = enrich_scene_graph(graph)
    in_front = [
        c for c in graph.constraints if c.type == ConstraintType.IN_FRONT_OF
    ]
    assert len(in_front) == 2
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
        constraints=[],
    )
    graph = enrich_scene_graph(graph)
    assert any(c.type == ConstraintType.SEATS_AROUND for c in graph.constraints)
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
    graph = MockLLMProvider().generate_scene_graph(room)
    ids = {f.id for f in graph.furniture}
    assert "nightstand_l" in ids or any("nightstand" in i for i in ids)
