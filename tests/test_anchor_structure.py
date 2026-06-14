"""Anchor zones: count by room size, min children per anchor."""

from colayout.catalog.kenney_index import role_for_model
from colayout.llm.anchor_structure import (
    MIN_CHILDREN_PER_ANCHOR,
    anchor_count_for_room,
    build_anchor_debug,
    check_anchor_structure,
    check_orphan_placements,
    count_anchor_children,
    ensure_anchor_children,
    min_children_for_anchor,
    resolve_anchor_placements,
)
from colayout.llm.provider import MockLLMProvider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec


def test_anchor_count_scales_with_room_size():
    compact_lr = RoomSpec(id="c", type="living_room", width_m=3.0, length_m=3.5)
    spacious_lr = RoomSpec(id="s", type="living_room", width_m=5.5, length_m=5.5)
    assert anchor_count_for_room(compact_lr) == 2
    assert anchor_count_for_room(spacious_lr) == 3

    compact_br = RoomSpec(id="b", type="bedroom", width_m=3.0, length_m=3.5)
    standard_br = RoomSpec(id="b2", type="bedroom", width_m=4.0, length_m=3.5)
    spacious_br = RoomSpec(id="b3", type="bedroom", width_m=5.5, length_m=5.5)
    assert anchor_count_for_room(compact_br) == 1
    assert anchor_count_for_room(standard_br) == 2
    assert anchor_count_for_room(spacious_br) == 3


def test_mock_living_standard_has_two_anchors_with_children():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, errors = validate_layout_draft(draft, room)
    anchors = resolve_anchor_placements(draft.placements, room)
    assert len(anchors) == 2
    tv = next(a for a in anchors if a.id == "tv")
    assert role_for_model(tv.model_id) == "tv"
    assert tv.on_surface_of == "tv_console"
    anchor_ids = {a.id for a in anchors}
    for anchor in anchors:
        from colayout.llm.anchor_structure import _anchor_role_for_placement

        role = _anchor_role_for_placement(anchor)
        required = min_children_for_anchor(room.type, role)
        assert (
            count_anchor_children(
                anchor.id, draft.placements, other_anchor_ids=anchor_ids
            )
            >= required
        )
    assert check_orphan_placements(draft.placements, room) is None
    orphan_msgs = [e for e in errors if "orphan" in e]
    assert not orphan_msgs


def test_mock_living_spacious_has_three_anchors_with_children():
    room = RoomSpec(id="lr", type="living_room", width_m=5.5, length_m=5.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, errors = validate_layout_draft(draft, room)
    anchors = resolve_anchor_placements(draft.placements, room)
    assert len(anchors) == 3
    tv = next(a for a in anchors if a.id == "tv")
    assert role_for_model(tv.model_id) == "tv"
    anchor_ids = {a.id for a in anchors}
    for anchor in anchors:
        from colayout.llm.anchor_structure import _anchor_role_for_placement

        role = _anchor_role_for_placement(anchor)
        required = min_children_for_anchor(room.type, role)
        assert (
            count_anchor_children(
                anchor.id, draft.placements, other_anchor_ids=anchor_ids
            )
            >= required
        )
    assert check_orphan_placements(draft.placements, room) is None
    assert not [e for e in errors if "orphan" in e]


def test_ensure_anchor_children_adds_missing_anchors_not_child_furniture():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

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
                relative_to="tv",
            ),
            FurniturePlacementDraft(
                id="tv",
                model_id="televisionModern",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=3.05,
                composition_role="anchor",
                on_surface_of="tv_console",
            ),
            FurniturePlacementDraft(
                id="tv_console",
                model_id="sideTable",
                placement_order=3,
                center_x_m=2.0,
                center_z_m=3.0,
                relative_to="tv",
            ),
        ],
    )
    expanded, msgs = ensure_anchor_children(draft, room)
    assert not any("auto-added child" in m for m in msgs)
    assert any(p.id == "bookshelf" for p in expanded.placements)
    assert check_orphan_placements(expanded.placements, room) is None


def test_min_children_dict_per_anchor_role():
    assert min_children_for_anchor("bedroom", "bed") == 4
    assert min_children_for_anchor("bedroom", "desk") >= 1
    assert min_children_for_anchor("bedroom", "dresser") >= 1
    assert min_children_for_anchor("kitchen", "sink") == 2
    assert MIN_CHILDREN_PER_ANCHOR["living_room"]["tv"] == 4


def test_spacious_bedroom_has_dresser_anchor():
    room = RoomSpec(id="bed", type="bedroom", width_m=5.5, length_m=5.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    anchors = resolve_anchor_placements(draft.placements, room)
    assert len(anchors) == 3
    roles = {role_for_model(a.model_id) for a in anchors}
    assert roles == {"bed", "desk", "dresser"}
    dresser = next(a for a in anchors if role_for_model(a.model_id) == "dresser")
    assert dresser.relative_to is None


def test_build_anchor_debug_tree():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    debug = build_anchor_debug(draft.placements, room)
    assert debug["anchor_count"] == 2
    assert len(debug["anchors"]) == 2
    bed = next(a for a in debug["anchors"] if a["role"] == "bed")
    assert bed["child_count"] >= min_children_for_anchor("bedroom", "bed")
    assert all("id" in c for c in bed["children"])
    bed_child_ids = {c["id"] for c in bed["children"]}
    assert "desk" not in bed_child_ids


def test_desk_anchor_is_its_own_zone_not_bed_child():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    anchors = resolve_anchor_placements(draft.placements, room)
    anchor_ids = {a.id for a in anchors}
    desk = next(a for a in anchors if role_for_model(a.model_id) == "desk")
    assert desk.relative_to is None
    assert count_anchor_children("bed", draft.placements, other_anchor_ids=anchor_ids) >= 4
    assert count_anchor_children(desk.id, draft.placements, other_anchor_ids=anchor_ids) >= 1


def test_orphan_placements_warn_when_not_in_anchor_group():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

    draft = RoomLayoutDraft(
        room_id="bed",
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
                id="stray_plant",
                model_id="pottedPlant",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=1.0,
            ),
        ],
    )
    msg = check_orphan_placements(draft.placements, room)
    assert msg is not None
    assert "stray_plant" in msg


def test_mock_bedroom_has_no_orphan_placements():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    assert check_orphan_placements(draft.placements, room) is None


def test_validate_passes_anchor_structure_for_mock_bedroom():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    _, errors = validate_layout_draft(draft, room)
    anchor_warnings = [e for e in errors if "anchor" in e.lower() and "children" in e.lower()]
    assert not anchor_warnings
