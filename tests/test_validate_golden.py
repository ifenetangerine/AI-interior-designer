"""Golden editor validation must not mutate author layouts like the LLM pipeline."""

from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    validate_golden_layout_draft,
    validate_layout_draft,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def _living_room_many_pieces(n: int) -> RoomLayoutDraft:
  placements = [
      FurniturePlacementDraft(
          id=f"decor_{i}",
          model_id="loungeSofa" if i == 1 else "sideTable",
          placement_order=i,
          center_x_m=1.0 + i * 0.4,
          center_z_m=1.5,
          orientation=0,
      )
      for i in range(1, n + 1)
  ]
  return RoomLayoutDraft(room_id="lr", room_type="living_room", placements=placements)


def test_golden_validate_keeps_all_pieces_no_auto_add():
    room = RoomSpec(id="lr", type="living_room", width_m=5.0, length_m=4.5)
    draft = _living_room_many_pieces(12)
    sanitized, errors = validate_golden_layout_draft(draft, room)
    assert len(sanitized.placements) == 12
    assert not any("truncated" in e for e in errors)
    assert not any("auto-added" in e for e in errors)
    assert not any("linked orphan" in e for e in errors)
    assert not any("overlap" in e for e in errors)


def test_pipeline_validate_still_expands_sparse_drafts():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
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
        ],
    )
    sanitized, errors = validate_layout_draft(draft, room)
    assert len(sanitized.placements) > 1
    assert any("auto-added" in e for e in errors)


def test_golden_validate_passes_without_design_warnings():
    room = RoomSpec(id="lr", type="living_room", width_m=5.0, length_m=4.5)
    draft = _living_room_many_pieces(8)
    _, errors = validate_golden_layout_draft(draft, room)
    blocking = [e for e in errors if is_blocking_placement_error(e)]
    assert not blocking
