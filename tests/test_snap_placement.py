"""Wall snap for LLM placement drafts."""

from colayout.catalog.kenney_index import footprint_for_model
from colayout.llm.snap_placement import snap_placements_to_walls
from colayout.llm.validate_placement import validate_layout_draft
from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_snap_centered_bed_to_west_wall():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="r1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=1.75,
                orientation=0,
            ),
        ],
    )
    snapped = snap_placements_to_walls(draft, room)
    bed = snapped.placements[0]
    w, d = footprint_for_model("bedDouble")
    half_x = d / 2 if bed.orientation == 1 else w / 2
    assert bed.center_x_m <= half_x + 0.15
    assert bed.orientation == 1


def test_validate_snaps_centered_live_style_draft():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="r1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=1.75,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="wardrobe",
                model_id="cabinetBed",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=3.0,
                orientation=0,
            ),
        ],
    )
    sanitized, _ = validate_layout_draft(draft, room)
    bed = next(p for p in sanitized.placements if p.id == "bed")
    assert bed.center_x_m < 1.0


def test_mock_refine_pipeline_succeeds():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), 0.25, placement_mode="llm_refine"
    )
    assert bundle is not None
    bed = next(f for f in bundle.placement.furniture if f.id == "bed")
    assert bed.origin_i >= 0
