"""Tests for LLM layout draft validation."""

from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    validate_layout_draft,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def _bedroom_draft(**kwargs) -> RoomLayoutDraft:
    defaults = dict(
        room_id="r1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=1.0,
                center_z_m=1.75,
                orientation=1,
            ),
            FurniturePlacementDraft(
                id="wardrobe",
                model_id="cabinetBed",
                placement_order=2,
                center_x_m=2.2,
                center_z_m=3.1,
                orientation=0,
            ),
        ],
    )
    defaults.update(kwargs)
    return RoomLayoutDraft(**defaults)


def test_validate_accepts_cross_room_models():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = _bedroom_draft(
        placements=[
            FurniturePlacementDraft(
                id="stove",
                model_id="kitchenStove",
                placement_order=1,
                center_x_m=1.0,
                center_z_m=1.0,
                orientation=0,
            ),
        ]
    )
    sanitized, errors = validate_layout_draft(draft, room)
    stove = next((p for p in sanitized.placements if p.id == "stove"), None)
    assert stove is not None
    assert stove.model_id == "kitchenStove"
    assert not any("unknown model_id" in e for e in errors)


def test_validate_rejects_unknown_model():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = _bedroom_draft(
        placements=[
            FurniturePlacementDraft(
                id="x",
                model_id="notARealKenneyModel",
                placement_order=1,
                center_x_m=1.0,
                center_z_m=1.0,
                orientation=0,
            ),
        ]
    )
    sanitized, errors = validate_layout_draft(draft, room)
    assert len(sanitized.placements) == 0
    assert any("unknown model_id" in e for e in errors)


def test_validate_bounds_and_order():
    room = RoomSpec(id="r1", type="bedroom", width_m=3.0, length_m=3.0)
    draft = _bedroom_draft(
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=0.9,
                center_z_m=1.5,
                orientation=1,
            ),
            FurniturePlacementDraft(
                id="wardrobe",
                model_id="cabinetBed",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=2.5,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="nightstand",
                model_id="sideTable",
                placement_order=3,
                center_x_m=0.5,
                center_z_m=0.7,
                orientation=1,
            ),
            FurniturePlacementDraft(
                id="desk",
                model_id="desk",
                placement_order=4,
                center_x_m=2.2,
                center_z_m=1.5,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="desk_chair",
                model_id="chairDesk",
                placement_order=5,
                center_x_m=2.2,
                center_z_m=0.9,
                orientation=0,
            ),
        ]
    )
    sanitized, errors = validate_layout_draft(draft, room)
    assert len(sanitized.placements) == 5
    assert sanitized.placements[0].placement_order == 1
    assert not any("auto-added child" in e for e in errors)
    blocking = [e for e in errors if is_blocking_placement_error(e)]
    assert not blocking, blocking


def test_overlap_is_non_blocking():
    assert not is_blocking_placement_error(
        "overlap between 'a' and 'b' — IP refine will adjust"
    )
