"""Design principle validators."""

from colayout.llm.validate_principles import (
    check_lateral_balance,
    check_sofa_coffee_proportion,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft


def test_balance_warning_on_heavy_left():
    room = RoomSpec(id="r", type="living_room", width_m=4.0, length_m=3.5)
    placements = [
        FurniturePlacementDraft(
            id="sofa",
            model_id="loungeSofaLong",
            placement_order=1,
            center_x_m=0.8,
            center_z_m=1.0,
            orientation=0,
        ),
        FurniturePlacementDraft(
            id="wardrobe",
            model_id="cabinetBed",
            placement_order=2,
            center_x_m=0.6,
            center_z_m=3.0,
            orientation=0,
        ),
        FurniturePlacementDraft(
            id="bookshelf",
            model_id="bookcaseClosed",
            placement_order=3,
            center_x_m=0.5,
            center_z_m=2.0,
            orientation=0,
        ),
    ]
    msg = check_lateral_balance(placements, room)
    assert msg is not None
    assert "balance" in msg.lower()


def test_proportion_ok_for_standard_mock_spacing():
    placements = [
        FurniturePlacementDraft(
            id="sofa",
            model_id="loungeSofa",
            placement_order=1,
            center_x_m=2.0,
            center_z_m=0.9,
            orientation=0,
        ),
        FurniturePlacementDraft(
            id="coffee",
            model_id="tableCoffee",
            placement_order=2,
            center_x_m=2.0,
            center_z_m=1.3,
            orientation=0,
        ),
    ]
    assert check_sofa_coffee_proportion(placements) is None
