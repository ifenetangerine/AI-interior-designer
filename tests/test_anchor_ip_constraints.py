"""Anchor children get relative_position and symmetric_pair constraints for IP refine."""

from colayout.llm.anchor_structure import (
    anchor_relative_constraints,
    anchor_symmetric_pair_constraints,
)
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType


def test_bedroom_draft_emits_anchor_relative_constraints():
    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    rels = anchor_relative_constraints(draft.placements, room)
    assert len(rels) >= 4
    child_ids = {c.furniture_b for c in rels}
    assert "nightstand_l" in child_ids or "wardrobe" in child_ids


def test_scene_graph_includes_anchor_relative_constraints():
    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    rels = [c for c in graph.constraints if c.type == ConstraintType.RELATIVE_POSITION]
    assert len(rels) >= 4


def test_symmetric_pair_for_two_same_role_children():
    from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="b",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="desk",
                model_id="desk",
                placement_order=1,
                center_x_m=3.0,
                center_z_m=3.0,
                composition_role="anchor",
            ),
            FurniturePlacementDraft(
                id="plant_l",
                model_id="pottedPlant",
                placement_order=2,
                center_x_m=2.7,
                center_z_m=3.0,
                relative_to="desk",
            ),
            FurniturePlacementDraft(
                id="plant_r",
                model_id="pottedPlant",
                placement_order=3,
                center_x_m=3.3,
                center_z_m=3.0,
                relative_to="desk",
            ),
        ],
    )
    pairs = anchor_symmetric_pair_constraints(draft.placements, room)
    assert len(pairs) == 1
    assert pairs[0].furniture == "desk"
    assert pairs[0].axis == "j"


def test_living_room_tv_is_anchor_in_scene_graph():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    tv_items = [f for f in graph.furniture if f.id == "tv"]
    assert len(tv_items) == 1
    assert tv_items[0].model_id == "televisionModern"


def test_kitchen_dining_table_is_anchor():
    room = RoomSpec(id="k", type="kitchen", width_m=5.0, length_m=4.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    from colayout.llm.anchor_structure import zone_anchor_placements

    anchors = zone_anchor_placements(draft.placements, room)
    assert any(p.id == "dining_table" for p in anchors)


def test_dining_table_emits_chair_symmetric_pairs():
    from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

    room = RoomSpec(id="k", type="kitchen", width_m=5.0, length_m=4.0)
    draft = RoomLayoutDraft(
        room_id="k",
        room_type="kitchen",
        placements=[
            FurniturePlacementDraft(
                id="dining_table",
                model_id="table",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=1.2,
                composition_role="anchor",
            ),
            FurniturePlacementDraft(
                id="dining_chair_1",
                model_id="chair",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=0.5,
                relative_to="dining_table",
            ),
            FurniturePlacementDraft(
                id="dining_chair_2",
                model_id="chair",
                placement_order=3,
                center_x_m=2.0,
                center_z_m=1.9,
                relative_to="dining_table",
            ),
            FurniturePlacementDraft(
                id="dining_chair_3",
                model_id="chair",
                placement_order=4,
                center_x_m=1.2,
                center_z_m=1.2,
                orientation=1,
                relative_to="dining_table",
            ),
            FurniturePlacementDraft(
                id="dining_chair_4",
                model_id="chair",
                placement_order=5,
                center_x_m=2.8,
                center_z_m=1.2,
                orientation=1,
                relative_to="dining_table",
            ),
        ],
    )
    pairs = anchor_symmetric_pair_constraints(draft.placements, room)
    assert len(pairs) == 2
    assert pairs[0].furniture == "dining_table"
    j_pair = next(p for p in pairs if p.axis == "j")
    i_pair = next(p for p in pairs if p.axis == "i")
    assert {j_pair.furniture_a, j_pair.furniture_b} == {
        "dining_chair_1",
        "dining_chair_2",
    }
    assert {i_pair.furniture_a, i_pair.furniture_b} == {
        "dining_chair_3",
        "dining_chair_4",
    }

    graph = draft_to_scene_graph(draft, room)
    sym = [c for c in graph.constraints if c.type == ConstraintType.SYMMETRIC_PAIR]
    assert len(sym) == 2
