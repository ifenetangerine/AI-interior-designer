"""Tier expansion fills under-furnished living room drafts."""

from colayout.llm.expand_layout_draft import expand_layout_draft_for_tier
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def _minimal_living() -> RoomLayoutDraft:
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
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="tv",
                model_id="cabinetTelevision",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=3.0,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="coffee_table",
                model_id="tableCoffee",
                placement_order=3,
                center_x_m=2.0,
                center_z_m=1.7,
                orientation=0,
            ),
        ],
    )


def test_expand_adds_standard_decor():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = _minimal_living()
    expanded, msgs = expand_layout_draft_for_tier(draft, room)
    assert len(expanded.placements) >= 5
    roles = {p.model_id for p in expanded.placements}
    assert "rugRectangle" in roles or "lampRoundFloor" in roles
    assert any("auto-added" in m for m in msgs)


def test_validate_runs_expansion_for_sparse_draft():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = _minimal_living()
    sanitized, errors = validate_layout_draft(draft, room)
    assert len(sanitized.placements) >= 5
    assert any("auto-added" in e for e in errors)
