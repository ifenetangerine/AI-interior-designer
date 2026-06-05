"""Tests for layout draft → grid hint conversion."""

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import center_to_origin_cells, draft_to_hints
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_center_to_origin_cells():
    ox, oy = center_to_origin_cells(1.0, 1.75, 2.0, 1.6, 0.5, 8, 7)
    assert ox == 0
    assert oy == 2


def test_draft_to_hints_stable():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    grid = discretize_room(room, 0.5)
    draft = RoomLayoutDraft(
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
        ],
    )
    hints = draft_to_hints(draft, grid)
    assert "bed" in hints
    ox, oy, rot = hints["bed"]
    assert rot == 1
    assert ox >= 0
    assert oy >= 0
