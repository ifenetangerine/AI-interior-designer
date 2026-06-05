"""Tests for room program, density scaling, and category-aware enrich."""

from colayout.llm.design_rules import enrich_scene_graph
from colayout.llm.provider import MockLLMProvider, _is_blocking_error
from colayout.llm.room_program import (
    density_tier,
    furniture_count_bounds,
    room_area_m2,
)
from colayout.llm.validate import validate_and_sanitize
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def test_density_tiers():
    assert density_tier(9.0) == "compact"
    assert density_tier(18.0) == "standard"
    assert density_tier(30.0) == "spacious"


def test_enrich_links_by_category_ids():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="work_chair", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="study_desk", category="desk", width_m=1.0, length_m=0.6),
        ],
        constraints=[],
    )
    enriched = enrich_scene_graph(graph)
    types = {c.type for c in enriched.constraints}
    assert ConstraintType.IN_FRONT_OF in types
    in_front = next(
        c for c in enriched.constraints if c.type == ConstraintType.IN_FRONT_OF
    )
    assert in_front.furniture_a == "work_chair"
    assert in_front.furniture_b == "study_desk"


def test_orphan_validation_blocks():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="bed", category="bed", width_m=1.6, length_m=2.0),
            FurnitureItem(id="wardrobe", category="wardrobe", width_m=1.2, length_m=0.6),
            FurnitureItem(id="desk", category="desk", width_m=1.0, length_m=0.6),
                FurnitureItem(id="floater", model_id="plantSmall1"),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.AGAINST_WALL,
                furniture="bed",
                wall="west",
            ),
        ],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    _, errors = validate_and_sanitize(graph, room)
    assert any("orphan" in e and "floater" in e for e in errors)
    assert any(_is_blocking_error(e) for e in errors)


def test_mock_spacious_more_than_compact():
    compact = RoomSpec(id="c", type="bedroom", width_m=3.0, length_m=3.0)
    spacious = RoomSpec(id="s", type="bedroom", width_m=6.0, length_m=5.0)
    g_compact = MockLLMProvider().generate_scene_graph(compact)
    g_spacious = MockLLMProvider().generate_scene_graph(spacious)
    assert len(g_spacious.furniture) > len(g_compact.furniture)
    assert room_area_m2(spacious) > 25.0
    min_s, _ = furniture_count_bounds("bedroom", "spacious")
    assert len(g_spacious.furniture) >= min_s


def test_facing_approach_side_bedroom():
    from colayout.grid.discretize import discretize_room
    from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine

    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="work_chair", category="chair", width_m=0.5, length_m=0.5),
            FurnitureItem(id="study_desk", category="desk", width_m=1.2, length_m=0.6),
        ],
        constraints=[],
    )
    graph = enrich_scene_graph(graph)
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
