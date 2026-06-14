"""Config-driven furniture role → anchor relations."""

from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.relations.loader import validate_relation_config
from colayout.relations.resolver import resolve_role_constraints
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.scene import ConstraintType


def test_relation_config_validates_all_catalog_roles():
    errors = validate_relation_config()
    assert errors == [], errors


def test_living_room_rug_gets_centered_under_or_draft_stack():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="lr",
        room_type="living_room",
        placements=[
            FurniturePlacementDraft(
                id="tv",
                model_id="televisionModern",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=3.0,
                composition_role="anchor",
            ),
            FurniturePlacementDraft(
                id="sofa",
                model_id="loungeSofa",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=0.9,
                relative_to="tv",
            ),
            FurniturePlacementDraft(
                id="coffee_table",
                model_id="tableCoffee",
                placement_order=3,
                center_x_m=2.0,
                center_z_m=1.7,
                relative_to="sofa",
            ),
            FurniturePlacementDraft(
                id="rug",
                model_id="rugRectangle",
                placement_order=4,
                center_x_m=2.0,
                center_z_m=1.7,
            ),
        ],
    )
    constraints = resolve_role_constraints(draft, room, [])
    rugs = [c for c in constraints if c.type == ConstraintType.CENTERED_UNDER]
    assert rugs
    assert rugs[0].furniture_b == "coffee_table"
    assert rugs[0].hard is False


def test_bedroom_nightstand_flank_is_soft():
    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    constraints = resolve_role_constraints(draft, room, [])
    flanks = [c for c in constraints if c.type == ConstraintType.FLANK]
    assert flanks
    assert all(not c.hard for c in flanks)


def test_kitchen_chair_seats_around_dining_table():
    room = RoomSpec(id="k", type="kitchen", width_m=5.0, length_m=4.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    constraints = resolve_role_constraints(draft, room, [])
    seats = [c for c in constraints if c.type == ConstraintType.SEATS_AROUND]
    assert seats
    assert seats[0].furniture == "dining_table"
    assert not seats[0].hard


def test_graph_includes_config_constraints():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    types = {c.type for c in graph.constraints}
    assert ConstraintType.FACING in types or ConstraintType.CENTERED_UNDER in types


def test_skips_when_draft_already_links_lamp():
    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="b",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=0.6,
                center_z_m=1.75,
                composition_role="anchor",
            ),
            FurniturePlacementDraft(
                id="nightstand_l",
                model_id="sideTable",
                placement_order=2,
                center_x_m=0.55,
                center_z_m=0.85,
                relative_to="bed",
            ),
            FurniturePlacementDraft(
                id="lamp",
                model_id="lampSquareTable",
                placement_order=3,
                center_x_m=0.55,
                center_z_m=0.85,
                relative_to="nightstand_l",
                on_surface_of="nightstand_l",
            ),
        ],
    )
    extra = resolve_role_constraints(draft, room, [])
    lamp_on_top = [
        c
        for c in extra
        if c.type == ConstraintType.ON_TOP_OF and c.furniture_a == "lamp"
    ]
    assert not lamp_on_top
