"""Tests for fuzzy model_id repair."""

from colayout.catalog.fix_model_id import closest_catalog_id, fix_model_id
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_fix_common_hallucinations():
    assert fix_model_id("tableLamp", "bedroom")[0] == "lampSquareTable"
    assert fix_model_id("plantPot", "living_room")[0] == "pottedPlant"
    assert fix_model_id("chairArmchair", "living_room")[0] == "loungeChair"


def test_closest_catalog_id_deterministic():
    a = closest_catalog_id("tableLamp", "bedroom")
    b = closest_catalog_id("tableLamp", "bedroom")
    assert a == b


def test_validate_fixes_unknown_model_id():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="r1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="lamp",
                model_id="tableLamp",
                placement_order=1,
                center_x_m=1.0,
                center_z_m=1.0,
                orientation=0,
            ),
        ],
    )
    sanitized, msgs = validate_layout_draft(draft, room)
    assert len(sanitized.placements) == 1
    assert sanitized.placements[0].model_id == "lampSquareTable"
    assert any("fixed model_id" in m for m in msgs)
