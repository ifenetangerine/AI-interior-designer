"""Sequential planner merge and message helpers."""

from colayout.llm.placement_clamp import clamp_row_centers
from colayout.llm.sequential_planner import (
    _placement_from_llm_row,
    _merge_placements,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft


def test_merge_placements_renumbers():
    anchors = [
        FurniturePlacementDraft(
            id="bed",
            model_id="bedDouble",
            placement_order=1,
            center_x_m=1,
            center_z_m=1,
            composition_role="anchor",
        ),
    ]
    children = [
        FurniturePlacementDraft(
            id="ns1",
            model_id="sideTable",
            placement_order=5,
            center_x_m=0.5,
            center_z_m=1,
            relative_to="bed",
        ),
        FurniturePlacementDraft(
            id="bed",
            model_id="bedDouble",
            placement_order=99,
            center_x_m=1,
            center_z_m=1,
        ),
    ]
    merged = _merge_placements(anchors, children)
    assert len(merged) == 2
    assert merged[0].placement_order == 1
    assert merged[1].placement_order == 2
    assert merged[1].id == "ns1"


def test_clamp_row_centers_fixes_negative_z():
    room = RoomSpec(id="lr", type="living_room", width_m=5.5, length_m=4.5)
    warnings: list[str] = []
    row = clamp_row_centers(
        {
            "id": "sofa_1",
            "model_id": "loungeSofa",
            "furniture_role": "sofa",
            "center_x_m": 2.0,
            "center_z_m": -0.5,
            "orientation": 0,
        },
        room,
        warnings,
    )
    assert row["center_z_m"] >= 0
    assert warnings


def test_placement_from_llm_row_accepts_clamped_negative_coords():
    room = RoomSpec(id="lr", type="living_room", width_m=5.5, length_m=4.5)
    warnings: list[str] = []
    p = _placement_from_llm_row(
        {
            "id": "sofa_1",
            "furniture_role": "sofa",
            "placement_order": 2,
            "center_x_m": 2.0,
            "center_z_m": -0.5,
            "orientation": 0,
            "relative_to": "anchor_tv",
        },
        room,
        warnings,
    )
    assert p.center_z_m >= 0
