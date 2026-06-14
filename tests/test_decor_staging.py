"""Decor staging program and auto-constraints."""

from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.llm.room_program import check_decor_staging
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType


def test_spacious_living_mock_has_decor_roles():
    room = RoomSpec(id="lr", type="living_room", width_m=6.0, length_m=5.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    model_ids = [p.model_id for p in draft.placements]
    assert check_decor_staging(model_ids, room) == []


def test_spacious_living_graph_has_decor_constraints():
    room = RoomSpec(id="lr", type="living_room", width_m=6.0, length_m=5.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    types = {c.type for c in graph.constraints}
    assert (
        ConstraintType.ON_TOP_OF in types
        or ConstraintType.UNDER in types
        or ConstraintType.CENTERED_UNDER in types
    )
    assert ConstraintType.AGAINST_WALL in types


def test_standard_living_mock_meets_piece_minimum():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    assert len(draft.placements) >= 5


def test_bedroom_lamps_keep_explicit_stack_parents():
    """Decor auto-link must not re-pair lamps already on_surface_of another piece."""
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    on_top = {
        (c.furniture_a, c.furniture_b)
        for c in graph.constraints
        if c.type == ConstraintType.ON_TOP_OF
    }
    assert ("bedside_lamp", "nightstand_l") in on_top
    assert ("desk_lamp", "desk") in on_top
    assert ("desk_lamp", "nightstand_r") not in on_top
