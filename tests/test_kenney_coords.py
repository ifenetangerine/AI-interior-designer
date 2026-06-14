"""Kenney placement uses footprint-aligned world coordinates."""

import math

from colayout.assets.kenney import (
    center_from_footprint,
    footprint_from_placed,
    match_kenney_assets,
    tight_footprint_from_placed,
)
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult


def test_footprint_from_origin_cells():
    f = PlacedFurniture(
        id="bed",
        category="bed",
        origin_i=0,
        origin_j=2,
        width_cells=4,
        length_cells=4,
        orientation=0,
        width_m=1.6,
        length_m=2.0,
        centroid_i=2.0,
        centroid_j=4.0,
    )
    x0, z0, x1, z1 = footprint_from_placed(f, 0.5)
    assert x0 == 0.0
    assert z0 == 1.0
    assert x1 == 2.0
    assert z1 == 3.0
    cx, cz = center_from_footprint(x0, z0, x1, z1)
    assert cx == 1.0
    assert cz == 2.0


def test_tight_footprint_smaller_than_grid_cells():
    f = PlacedFurniture(
        id="bed",
        category="bed",
        origin_i=0,
        origin_j=2,
        width_cells=5,
        length_cells=4,
        orientation=1,
        width_m=0.956,
        length_m=1.125,
        centroid_i=2.5,
        centroid_j=4.0,
    )
    gx0, gz0, gx1, gz1 = footprint_from_placed(f, 0.25)
    tx0, tz0, tx1, tz1 = tight_footprint_from_placed(f, 0.25)
    assert (gx1 - gx0) * (gz1 - gz0) > (tx1 - tx0) * (tz1 - tz0)
    assert abs((tx0 + tx1) / 2 - (gx0 + gx1) / 2) < 0.01


def test_match_kenney_no_half_cell_offset():
    placement = RoomPlacementResult(
        room_id="r1",
        room_type="bedroom",
        grid_w=8,
        grid_l=7,
        modulor_cell_m=0.5,
        width_m=4.0,
        length_m=3.5,
        furniture=[
            PlacedFurniture(
                id="bed",
                category="bed",
                origin_i=0,
                origin_j=0,
                width_cells=4,
                length_cells=4,
                orientation=0,
                width_m=1.6,
                length_m=2.0,
                centroid_i=2.0,
                centroid_j=2.0,
            ),
        ],
        cell_map=[[None] * 7 for _ in range(8)],
    )
    results = match_kenney_assets(placement)
    assert len(results) == 1
    p = results[0]
    assert p.position_m[0] == 1.0
    assert p.position_m[2] == 1.0
    assert p.footprint_m[1] == 0.0 and p.footprint_m[3] == 2.0
    assert math.isclose(p.footprint_m[0], 0.2, abs_tol=1e-6)
    assert math.isclose(p.footprint_m[2], 1.8, abs_tol=1e-6)


def test_bed_rot1_yaw_180():
    placement = RoomPlacementResult(
        room_id="r1",
        room_type="bedroom",
        grid_w=16,
        grid_l=14,
        modulor_cell_m=0.25,
        width_m=4.0,
        length_m=3.5,
        furniture=[
            PlacedFurniture(
                id="bed",
                category="bed",
                origin_i=0,
                origin_j=2,
                width_cells=8,
                length_cells=4,
                orientation=1,
                width_m=1.6,
                length_m=2.0,
                centroid_i=4.0,
                centroid_j=3.0,
            ),
        ],
        cell_map=[[None] * 14 for _ in range(16)],
    )
    results = match_kenney_assets(placement)
    yaw = results[0].rotation_y_rad % (2 * math.pi)
    assert math.isclose(yaw, math.radians(270.0), abs_tol=1e-6)


def test_chair_yaw_offset_applied():
    placement = RoomPlacementResult(
        room_id="r1",
        room_type="bedroom",
        grid_w=8,
        grid_l=7,
        modulor_cell_m=0.5,
        width_m=4.0,
        length_m=3.5,
        furniture=[
            PlacedFurniture(
                id="chair1",
                category="chair",
                origin_i=4,
                origin_j=4,
                width_cells=1,
                length_cells=1,
                orientation=0,
                width_m=0.5,
                length_m=0.5,
                centroid_i=4.5,
                centroid_j=4.5,
            ),
        ],
        cell_map=[[None] * 7 for _ in range(8)],
    )
    results = match_kenney_assets(placement)
    yaw = results[0].rotation_y_rad % (2 * math.pi)
    assert math.isclose(yaw, math.radians(180.0), abs_tol=1e-6)
