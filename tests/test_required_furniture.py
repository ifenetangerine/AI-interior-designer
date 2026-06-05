"""Required furniture roles per room type."""

from colayout.llm.provider import MockLLMProvider
from colayout.llm.room_program import check_required_furniture
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_bedroom_missing_wardrobe_blocks():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="r1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed", model_id="bedDouble", placement_order=1,
                center_x_m=0.56, center_z_m=1.75, orientation=1,
            ),
        ],
    )
    errs = check_required_furniture([p.model_id for p in draft.placements], "bedroom")
    assert any("wardrobe" in e for e in errs)


def test_kitchen_requires_counter_segments():
    room = RoomSpec(id="k1", type="kitchen", width_m=5.0, length_m=4.0)
    draft = RoomLayoutDraft(
        room_id="k1",
        room_type="kitchen",
        placements=[
            FurniturePlacementDraft(
                id="table", model_id="table", placement_order=1,
                center_x_m=2.5, center_z_m=1.5, orientation=0,
            ),
            FurniturePlacementDraft(
                id="sink", model_id="kitchenSink", placement_order=2,
                center_x_m=0.5, center_z_m=3.4, orientation=1,
            ),
            FurniturePlacementDraft(
                id="stove", model_id="kitchenStove", placement_order=3,
                center_x_m=2.0, center_z_m=3.4, orientation=1,
            ),
            FurniturePlacementDraft(
                id="fridge", model_id="kitchenFridge", placement_order=4,
                center_x_m=4.5, center_z_m=0.5, orientation=0,
            ),
            FurniturePlacementDraft(
                id="chair", model_id="chair", placement_order=5,
                center_x_m=2.5, center_z_m=0.7, orientation=0,
            ),
        ],
    )
    errs = check_required_furniture([p.model_id for p in draft.placements], "kitchen")
    assert any("counter" in e for e in errs)


def test_standard_living_room_mock_has_five_plus_pieces():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    assert len(draft.placements) >= 5
