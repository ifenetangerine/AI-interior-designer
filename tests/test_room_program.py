"""Tests for room program density scaling and draft-pipeline coverage."""

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.llm.room_program import (
    density_tier,
    furniture_count_bounds,
    room_area_m2,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine


def test_density_tiers():
    assert density_tier(9.0) == "compact"
    assert density_tier(18.0) == "standard"
    assert density_tier(30.0) == "spacious"


def test_config_links_desk_chair():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    in_front = [
        c for c in graph.constraints if c.type == ConstraintType.IN_FRONT_OF
    ]
    assert in_front, "expected chair in_front_of desk from config relations"


def test_mock_spacious_more_than_compact():
    compact = RoomSpec(id="c", type="bedroom", width_m=3.0, length_m=3.0)
    spacious = RoomSpec(id="s", type="bedroom", width_m=6.0, length_m=5.0)
    d_compact = MockLLMProvider().generate_layout_draft(compact)
    d_spacious = MockLLMProvider().generate_layout_draft(spacious)
    assert len(d_spacious.placements) > len(d_compact.placements)
    assert room_area_m2(spacious) > 25.0
    min_s, _ = furniture_count_bounds("bedroom", "spacious")
    assert len(d_spacious.placements) >= min_s


def test_facing_approach_side_bedroom():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="work_chair", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="study_desk", category="desk", width_m=1.2, length_m=0.6),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.AGAINST_WALL, furniture="study_desk", wall="east"
            ),
            FurnitureConstraint(
                type=ConstraintType.IN_FRONT_OF,
                furniture_a="work_chair",
                furniture_b="study_desk",
                distance_m=0.7,
            ),
        ],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    grid = discretize_room(room, 0.5)
    result = solve_room_coarse_to_fine(graph, grid, coarse_scale=2, time_limit_s=20)
    assert result is not None
    chair = next(f for f in result.furniture if f.id == "work_chair")
    desk = next(f for f in result.furniture if f.id == "study_desk")
    # Chair approaches desk along front axis (+i or +j depending on rot).
    assert (
        chair.centroid_i < desk.centroid_i - 0.2
        or chair.centroid_j < desk.centroid_j - 0.2
    )
