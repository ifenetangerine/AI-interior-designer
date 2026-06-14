"""Surface stacking: lamps on tables, rugs under coffee table."""

from colayout.assets.kenney import match_kenney_assets, load_kenney_catalog
from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import (
    _resolve_surface_parent,
    draft_to_hints,
    draft_to_scene_graph,
    placement_result_from_draft,
)
from colayout.llm.provider import MockLLMProvider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.scene import ConstraintType


def test_bedroom_refine_keeps_lamp_on_nightstand():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    lamp = next(
        p for p in draft.placements
        if p.on_surface_of and p.on_surface_of.startswith("nightstand")
    )
    ns = next(p for p in draft.placements if p.id == lamp.on_surface_of)
    assert abs(lamp.center_x_m - ns.center_x_m) < 0.15
    grid = discretize_room(room, 0.25)
    graph = draft_to_scene_graph(draft, room)
    stack_types = {c.type for c in graph.constraints}
    assert ConstraintType.ON_TOP_OF in stack_types
    result = solve_room_placement(
        graph,
        grid,
        SolveConfig(hints=draft_to_hints(draft, grid), soft_constraints=True, time_limit_s=15),
    )
    assert result is not None
    by_id = {f.id: f for f in result.furniture}
    assert lamp.id in by_id and ns.id in by_id
    assert by_id[lamp.id].stack_parent_id == ns.id
    assert by_id[lamp.id].origin_i == by_id[ns.id].origin_i
    assert by_id[lamp.id].origin_j == by_id[ns.id].origin_j


def test_stacked_lamp_has_vertical_position():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(room, MockLLMProvider(), 0.25)
    assert bundle is not None
    placements = match_kenney_assets(bundle.placement, load_kenney_catalog())
    elevated = [p for p in placements if p.position_m[1] > 0.05]
    assert len(elevated) >= 1


def test_living_rug_under_coffee_table():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    under = [
        c
        for c in graph.constraints
        if c.type in (ConstraintType.UNDER, ConstraintType.CENTERED_UNDER)
    ]
    assert len(under) >= 1


def test_rug_stays_on_floor_not_table_height():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(room, MockLLMProvider(), 0.25)
    assert bundle is not None
    rug = next(f for f in bundle.placement.furniture if f.id == "rug")
    coffee = next(f for f in bundle.placement.furniture if f.id == "coffee_table")
    assert rug.stack_mode == "under"
    assert rug.stack_parent_id == coffee.id
    placements = match_kenney_assets(bundle.placement, load_kenney_catalog())
    rug_p = next(p for p in placements if "rug" in p.model_id.lower())
    coffee_p = next(p for p in placements if "coffee" in p.model_id.lower())
    # Rug sits at the small anti-z-fighting offset, never at table height.
    assert 0.0 < rug_p.position_m[1] < 0.02
    assert coffee_p.position_m[1] < 0.05


def _living_room_bad_table_stack_draft() -> RoomLayoutDraft:
    return RoomLayoutDraft(
        room_id="lr",
        room_type="living_room",
        placements=[
            FurniturePlacementDraft(
                id="sofa",
                model_id="loungeSofa",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=0.9,
            ),
            FurniturePlacementDraft(
                id="coffee_table",
                model_id="tableCoffee",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=0.9,
                relative_to="sofa",
                on_surface_of="sofa",
            ),
        ],
    )


def test_coffee_table_on_surface_of_sofa_does_not_stack():
    draft = _living_room_bad_table_stack_draft()
    by_id = {p.id: p for p in draft.placements}
    coffee = by_id["coffee_table"]
    assert _resolve_surface_parent(coffee, by_id) is None

    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    sanitized, msgs = validate_layout_draft(draft, room)
    assert any("on_surface_of" in m for m in msgs)
    coffee_s = next(p for p in sanitized.placements if p.id == "coffee_table")
    assert coffee_s.on_surface_of is None

    grid = discretize_room(room, 0.25)
    placement = placement_result_from_draft(sanitized, grid)
    by_fid = {f.id: f for f in placement.furniture}
    assert by_fid["coffee_table"].stack_parent_id is None
    assert (
        by_fid["coffee_table"].origin_i != by_fid["sofa"].origin_i
        or by_fid["coffee_table"].origin_j != by_fid["sofa"].origin_j
    )


def test_rug_on_surface_of_sofa_still_under_stacks():
    draft = RoomLayoutDraft(
        room_id="lr",
        room_type="living_room",
        placements=[
            FurniturePlacementDraft(
                id="sofa",
                model_id="loungeSofa",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=0.9,
            ),
            FurniturePlacementDraft(
                id="rug",
                model_id="rugRectangle",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=0.9,
                relative_to="sofa",
                on_surface_of="sofa",
            ),
        ],
    )
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    sanitized, _ = validate_layout_draft(draft, room)
    rug = next(p for p in sanitized.placements if p.id == "rug")
    assert rug.on_surface_of == "sofa"

    grid = discretize_room(room, 0.25)
    placement = placement_result_from_draft(sanitized, grid)
    rug_p = next(f for f in placement.furniture if f.id == "rug")
    assert rug_p.stack_parent_id == "sofa"
    assert rug_p.stack_mode == "under"


def test_mock_llm_only_coffee_table_not_stacked_on_sofa():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), 0.25, placement_mode="llm_only"
    )
    assert bundle is not None
    by_id = {f.id: f for f in bundle.placement.furniture}
    assert "sofa" in by_id and "coffee_table" in by_id
    assert by_id["coffee_table"].stack_parent_id is None
    assert (
        by_id["coffee_table"].origin_i != by_id["sofa"].origin_i
        or by_id["coffee_table"].origin_j != by_id["sofa"].origin_j
    )
