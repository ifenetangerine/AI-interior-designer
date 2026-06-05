"""LLM refine pipeline: soft IP pass with hints."""

from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import draft_to_hints, draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_room
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_refine_with_hints_produces_feasible_layout():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    llm = MockLLMProvider()
    draft = llm.generate_layout_draft(room)
    grid = discretize_room(room, 0.5)
    hints = draft_to_hints(draft, grid)
    graph = draft_to_scene_graph(draft)

    result = solve_room_placement(
        graph,
        grid,
        SolveConfig(
            hints=hints,
            soft_constraints=True,
            time_limit_s=15.0,
        ),
    )
    assert result is not None
    assert len(result.furniture) == len(draft.placements)


def test_refine_resolves_overlap():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    grid = discretize_room(room, 0.5)
    draft = RoomLayoutDraft(
        room_id="r1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=1.75,
                orientation=1,
            ),
            FurniturePlacementDraft(
                id="wardrobe",
                model_id="cabinetBed",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=1.75,
                orientation=0,
            ),
        ],
    )
    hints = draft_to_hints(draft, grid)
    graph = draft_to_scene_graph(draft)
    result = solve_room_placement(
        graph,
        grid,
        SolveConfig(
            hints=hints,
            soft_constraints=True,
            time_limit_s=15.0,
        ),
    )
    assert result is not None
    assert len(result.furniture) == 2
    ids = {(f.origin_i, f.origin_j) for f in result.furniture}
    assert len(ids) == 2


def test_mock_llm_only_pipeline():
    room = RoomSpec(id="bed1", type="bedroom", width_m=4.0, length_m=3.5)
    from colayout.pipeline.place import place_room_with_graph

    bundle = place_room_with_graph(
        room, MockLLMProvider(), modulor_cell_m=0.5, placement_mode="llm_only"
    )
    assert bundle is not None
    assert bundle.layout_draft is not None
    assert len(bundle.placement.furniture) >= 2


def test_mock_llm_refine_pipeline():
    room = RoomSpec(id="bed1", type="bedroom", width_m=4.0, length_m=3.5)
    result = place_room(room, MockLLMProvider(), modulor_cell_m=0.5)
    assert result is not None
    assert len(result.furniture) >= 2


def test_llm_refine_nightstands_and_desk_chair():
    from colayout.pipeline.place import place_room_with_graph
    from colayout.schemas.scene import ConstraintType

    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), modulor_cell_m=0.25, placement_mode="llm_refine"
    )
    assert bundle is not None
    types = {c.type for c in bundle.scene_graph.constraints}
    assert ConstraintType.FLANK in types
    assert ConstraintType.IN_FRONT_OF in types

    bed = next(f for f in bundle.placement.furniture if f.id == "bed")
    left = next(f for f in bundle.placement.furniture if f.id == "nightstand_l")
    right = next(f for f in bundle.placement.furniture if f.id == "nightstand_r")
    desk = next(f for f in bundle.placement.furniture if f.id == "desk")
    chair = next(f for f in bundle.placement.furniture if f.id == "desk_chair")

    assert left.centroid_j < bed.centroid_j
    assert right.centroid_j > bed.centroid_j
    assert left.origin_i <= bed.origin_i + 1
    assert right.origin_i <= bed.origin_i + 1
    assert (
        chair.centroid_i < desk.centroid_i - 0.2
        or chair.centroid_j < desk.centroid_j - 0.2
    )
    assert (
        abs(chair.centroid_i - desk.centroid_i) <= 0.5
        or abs(chair.centroid_j - desk.centroid_j) <= 0.5
    )
