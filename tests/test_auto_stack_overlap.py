"""Auto-link stackable pieces when footprints overlap (golden editor)."""

import pytest

from colayout.assets.kenney import match_kenney_assets, load_kenney_catalog
from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import (
    auto_link_overlapping_stacks,
    placement_result_from_draft,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_lamp_on_desk_overlap_auto_links_and_elevates():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="test",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="desk_1",
                model_id="desk",
                placement_order=1,
                center_x_m=1.2,
                center_z_m=1.0,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="lamp_1",
                model_id="lampRoundTable",
                placement_order=2,
                center_x_m=1.2,
                center_z_m=1.0,
                orientation=0,
            ),
        ],
    )
    linked = auto_link_overlapping_stacks(list(draft.placements))
    lamp = next(p for p in linked if p.id == "lamp_1")
    assert lamp.on_surface_of == "desk_1"

    linked_draft = draft.model_copy(update={"placements": linked})
    grid = discretize_room(room, 0.25)
    placement = placement_result_from_draft(linked_draft, grid)
    lamp_p = next(f for f in placement.furniture if f.id == "lamp_1")
    assert lamp_p.stack_parent_id == "desk_1"

    kenney = match_kenney_assets(placement, load_kenney_catalog())
    lamp_k = next(k for k in kenney if k.furniture_id.endswith("lamp_1"))
    desk_k = next(k for k in kenney if k.furniture_id.endswith("desk_1"))
    assert lamp_k.position_m[1] > desk_k.position_m[1] + 0.05


def test_decor_on_counter_base_overlap_auto_links():
    room = RoomSpec(id="kit", type="kitchen", width_m=5.0, length_m=4.0)
    draft = RoomLayoutDraft(
        room_id="test",
        room_type="kitchen",
        placements=[
            FurniturePlacementDraft(
                id="cabinet_1",
                model_id="kitchenCabinet",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=3.5,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="decor_1",
                model_id="plantSmall1",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=3.5,
                orientation=0,
            ),
        ],
    )
    linked = auto_link_overlapping_stacks(list(draft.placements))
    decor = next(p for p in linked if p.id == "decor_1")
    assert decor.on_surface_of == "cabinet_1"


def test_golden_preview_preserves_sub_cell_centers():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="test",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="desk_1",
                model_id="desk",
                placement_order=1,
                center_x_m=1.51,
                center_z_m=2.13,
                orientation=0,
            ),
        ],
    )
    grid = discretize_room(room, 0.25)
    snapped = placement_result_from_draft(draft, grid)
    exact = placement_result_from_draft(draft, grid, preserve_centers=True)
    desk_snapped = next(f for f in snapped.furniture if f.id == "desk_1")
    desk_exact = next(f for f in exact.furniture if f.id == "desk_1")
    assert desk_snapped.centroid_i * 0.25 == pytest.approx(1.625, abs=1e-6)
    assert desk_exact.centroid_i * 0.25 == pytest.approx(1.51, abs=1e-6)
    assert desk_exact.centroid_j * 0.25 == pytest.approx(2.13, abs=1e-6)


def test_tv_on_table_overlap_auto_links_and_elevates():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="test",
        room_type="living_room",
        placements=[
            FurniturePlacementDraft(
                id="table_1",
                model_id="table",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=1.5,
                orientation=0,
            ),
            FurniturePlacementDraft(
                id="tv_1",
                model_id="televisionModern",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=1.5,
                orientation=0,
            ),
        ],
    )
    linked = auto_link_overlapping_stacks(list(draft.placements))
    tv = next(p for p in linked if p.id == "tv_1")
    assert tv.on_surface_of == "table_1"

    placement = placement_result_from_draft(
        draft.model_copy(update={"placements": linked}),
        discretize_room(room, 0.25),
        preserve_centers=True,
    )
    kenney = match_kenney_assets(placement, load_kenney_catalog())
    tv_k = next(k for k in kenney if k.furniture_id.endswith("tv_1"))
    table_k = next(k for k in kenney if k.furniture_id.endswith("table_1"))
    assert tv_k.position_m[1] > table_k.position_m[1] + 0.05


def test_stack_clears_when_dragged_apart():
    placements = [
        FurniturePlacementDraft(
            id="desk_1",
            model_id="desk",
            placement_order=1,
            center_x_m=1.0,
            center_z_m=1.0,
            orientation=0,
        ),
        FurniturePlacementDraft(
            id="lamp_1",
            model_id="lampRoundTable",
            placement_order=2,
            center_x_m=1.0,
            center_z_m=1.0,
            orientation=0,
            on_surface_of="desk_1",
        ),
    ]
    apart = [
        placements[0],
        placements[1].model_copy(update={"center_x_m": 3.0, "center_z_m": 3.0}),
    ]
    linked = auto_link_overlapping_stacks(apart)
    lamp = next(p for p in linked if p.id == "lamp_1")
    assert lamp.on_surface_of is None
