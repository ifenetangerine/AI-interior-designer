"""Tests for grid ↔ continuous domain transforms."""

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)
from colayout.solver.domain_transform import (
    furniture_positions_to_placement,
    grid_centroid_to_meters,
    meters_to_grid_centroid,
    placement_to_furniture_positions,
)
from colayout.solver.hybrid_adapters import draft_to_hybrid_state
from colayout.solver.hybrid_types import (
    FurnitureDimensions,
    FurniturePosition,
    HybridFurnitureItem,
    HybridPlacementState,
)


def test_grid_centroid_to_meters():
    x, z = grid_centroid_to_meters(8.0, 6.0, 0.25)
    assert abs(x - 2.0) < 1e-9
    assert abs(z - 1.5) < 1e-9
    ci, cj = meters_to_grid_centroid(x, z, 0.25)
    assert abs(ci - 8.0) < 1e-9
    assert abs(cj - 6.0) < 1e-9


def test_placement_round_trip():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    draft, _ = validate_layout_draft(draft, room)
    graph = draft_to_scene_graph(draft, room)
    grid = discretize_room(room, 0.25)
    state = draft_to_hybrid_state(draft, room, graph)

    from colayout.llm.draft_to_hints import placement_result_from_draft

    placement = placement_result_from_draft(draft, grid)
    positions = placement_to_furniture_positions(
        placement, grid, use_catalog_yaw=False
    )
    round_trip = furniture_positions_to_placement(state, positions, grid, graph)

    assert round_trip.room_id == placement.room_id
    assert len(round_trip.furniture) == len(placement.furniture)
    for orig, back in zip(
        sorted(placement.furniture, key=lambda f: f.id),
        sorted(round_trip.furniture, key=lambda f: f.id),
    ):
        if orig.stack_parent_id or back.stack_parent_id:
            continue
        assert orig.id == back.id
        assert abs(orig.centroid_i - back.centroid_i) <= 1.0
        assert abs(orig.centroid_j - back.centroid_j) <= 1.0


def test_facing_constraint_does_not_co_locate_on_export():
    """FACING is not a stack relation; child must keep its own footprint."""
    room = RoomSpec(id="r1", type="living_room", width_m=4.0, length_m=3.5)
    grid = discretize_room(room, 0.25)
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="living_room",
        furniture=[
            FurnitureItem(id="sofa", category="sofa", width_m=1.5, length_m=0.8),
            FurnitureItem(id="tv", category="tv", width_m=0.8, length_m=0.3),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.FACING,
                furniture_a="sofa",
                furniture_b="tv",
            ),
        ],
    )
    stage1 = RoomPlacementResult(
        room_id="r1",
        room_type="living_room",
        grid_w=grid.width_cells,
        grid_l=grid.length_cells,
        modulor_cell_m=grid.modulor_cell_m,
        width_m=room.width_m,
        length_m=room.length_m,
        furniture=[
            PlacedFurniture(
                id="sofa",
                category="sofa",
                origin_i=2,
                origin_j=4,
                width_cells=6,
                length_cells=3,
                orientation=0,
                width_m=1.5,
                length_m=0.8,
                centroid_i=5.0,
                centroid_j=5.5,
            ),
            PlacedFurniture(
                id="tv",
                category="tv",
                origin_i=2,
                origin_j=12,
                width_cells=3,
                length_cells=2,
                orientation=0,
                width_m=0.8,
                length_m=0.3,
                centroid_i=3.5,
                centroid_j=13.0,
            ),
        ],
        cell_map=[[None] * grid.length_cells for _ in range(grid.width_cells)],
    )
    state = HybridPlacementState(
        room_id="r1",
        room_type="living_room",
        width_m=room.width_m,
        length_m=room.length_m,
        items=[
            HybridFurnitureItem(
                id="sofa",
                dimensions=FurnitureDimensions(width_x=1.5, depth_z=0.8, height_y=0.5),
                initial_position=FurniturePosition(x=1.25, z=1.375, theta_deg=0.0),
                item_type="sofa",
                category="sofa",
                focal_target_id="tv",
            ),
            HybridFurnitureItem(
                id="tv",
                dimensions=FurnitureDimensions(width_x=0.8, depth_z=0.3, height_y=0.5),
                initial_position=FurniturePosition(x=0.875, z=3.25, theta_deg=180.0),
                item_type="tv",
                category="tv",
                focal_target_id="sofa",
            ),
        ],
    )
    positions = placement_to_furniture_positions(stage1, grid, use_catalog_yaw=False)
    exported = furniture_positions_to_placement(
        state, positions, grid, graph, stage1=stage1
    )
    sofa = next(f for f in exported.furniture if f.id == "sofa")
    tv = next(f for f in exported.furniture if f.id == "tv")
    assert sofa.stack_parent_id is None
    assert tv.stack_parent_id is None
    assert abs(sofa.centroid_i - tv.centroid_i) > 0.5
    assert abs(sofa.centroid_j - tv.centroid_j) > 0.5
