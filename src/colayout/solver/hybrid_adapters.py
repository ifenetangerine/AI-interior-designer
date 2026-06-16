"""Convert between hybrid solver state and pipeline draft/graph/placement types."""

from __future__ import annotations

from colayout.catalog.kenney_index import (
    footprint_for_model,
    height_for_model,
    placement_category,
    role_for_model,
)
from colayout.grid.discretize import GridSpec
from colayout.placement.orient import WALL_FACE_CATEGORIES
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.placement import RoomPlacementResult
from colayout.schemas.scene import ConstraintType, RoomSceneGraph
from colayout.solver.domain_transform import furniture_positions_to_placement
from colayout.solver.hybrid_types import (
    FurnitureDimensions,
    FurniturePosition,
    HybridFurnitureItem,
    HybridPlacementState,
)

FOCAL_PAIRS: dict[str, str] = {
    "sofa": "tv",
    "tv": "sofa",
    "chair": "desk",
    "desk_chair": "desk",
    "bar_stool": "counter_bar",
}


def _item_type_for_placement(p: FurniturePlacementDraft) -> str:
    role = role_for_model(p.model_id)
    cat = placement_category(p.model_id)
    if role in ("sofa", "tv", "desk", "bed", "dining_table", "coffee_table"):
        return role
    if cat in WALL_FACE_CATEGORIES and p.composition_role == "anchor":
        return "wall_anchor"
    return role or cat or "misc"


def _graph_focal_targets(graph: RoomSceneGraph) -> dict[str, str]:
    """Map furniture id -> focal target id from FACING / IN_FRONT_OF constraints."""
    targets: dict[str, str] = {}
    for c in graph.constraints:
        if c.type not in (ConstraintType.FACING, ConstraintType.IN_FRONT_OF):
            continue
        if not c.furniture_a or not c.furniture_b:
            continue
        targets[c.furniture_a] = c.furniture_b
    return targets


def _graph_wall_anchors(graph: RoomSceneGraph) -> set[str]:
    """Furniture ids with explicit AGAINST_WALL constraints."""
    anchors: set[str] = set()
    for c in graph.constraints:
        if c.type == ConstraintType.AGAINST_WALL and c.furniture:
            anchors.add(c.furniture)
    return anchors


def _is_wall_anchor(
    p: FurniturePlacementDraft,
    room: RoomSpec,
    graph: RoomSceneGraph,
) -> bool:
    cat = placement_category(p.model_id)
    if cat == "bed":
        return False
    if p.id in _graph_wall_anchors(graph):
        return True
    item_type = _item_type_for_placement(p)
    if item_type == "wall_anchor":
        return True
    cat = placement_category(p.model_id)
    if cat not in WALL_FACE_CATEGORIES:
        return False
    margin = 0.35
    return (
        p.center_x_m <= margin
        or p.center_z_m <= margin
        or p.center_x_m >= room.width_m - margin
        or p.center_z_m >= room.length_m - margin
    )


def _focal_target_id(
    p: FurniturePlacementDraft,
    by_id: dict[str, FurniturePlacementDraft],
    graph: RoomSceneGraph,
) -> str | None:
    graph_targets = _graph_focal_targets(graph)
    if p.id in graph_targets and graph_targets[p.id] in by_id:
        return graph_targets[p.id]
    if p.relative_to and p.relative_to in by_id:
        return p.relative_to
    item_type = _item_type_for_placement(p)
    for other in by_id.values():
        if other.id == p.id:
            continue
        other_type = _item_type_for_placement(other)
        if FOCAL_PAIRS.get(item_type) == other_type:
            return other.id
    return None


def draft_to_hybrid_state(
    draft: RoomLayoutDraft,
    room: RoomSpec,
    graph: RoomSceneGraph,
) -> HybridPlacementState:
    stack_parents = {
        c.furniture_a: c.furniture_b
        for c in graph.constraints
        if c.furniture_a and c.furniture_b
        and c.type.value in ("on_top_of", "under", "centered_under")
    }
    by_id = {p.id: p for p in draft.placements}
    items: list[HybridFurnitureItem] = []
    for p in sorted(draft.placements, key=lambda x: x.placement_order):
        w, d = footprint_for_model(p.model_id)
        h = height_for_model(p.model_id)
        theta_deg = float(p.orientation) * 90.0
        parent = stack_parents.get(p.id) or p.on_surface_of
        fixed = parent is not None
        items.append(
            HybridFurnitureItem(
                id=p.id,
                dimensions=FurnitureDimensions(
                    width_x=w,
                    depth_z=d,
                    height_y=h,
                ),
                initial_position=FurniturePosition(
                    x=p.center_x_m,
                    z=p.center_z_m,
                    theta_deg=theta_deg,
                ),
                item_type=_item_type_for_placement(p),
                model_id=p.model_id,
                category=placement_category(p.model_id),
                focal_target_id=_focal_target_id(p, by_id, graph),
                is_wall_anchor=_is_wall_anchor(p, room, graph),
                stack_parent_id=parent,
                fixed=fixed,
            )
        )
    return HybridPlacementState(
        room_id=room.id,
        room_type=room.type,
        width_m=room.width_m,
        length_m=room.length_m,
        items=items,
        architecture=room.architecture,
    )


def hybrid_state_to_placement_result(
    state: HybridPlacementState,
    grid: GridSpec,
    graph: RoomSceneGraph,
    positions: dict[str, FurniturePosition],
    stage1: RoomPlacementResult | None = None,
) -> RoomPlacementResult:
    """Convert hybrid continuous positions to grid placement (delegates to domain_transform)."""
    return furniture_positions_to_placement(
        state, positions, grid, graph, stage1=stage1
    )


def apply_positions_to_draft(
    draft: RoomLayoutDraft,
    positions: dict[str, FurniturePosition],
) -> RoomLayoutDraft:
    updated: list[FurniturePlacementDraft] = []
    for p in draft.placements:
        pos = positions.get(p.id)
        if not pos:
            updated.append(p)
            continue
        updated.append(
            p.model_copy(
                update={
                    "center_x_m": pos.x,
                    "center_z_m": pos.z,
                    "orientation": int(round(pos.theta_deg / 90.0)) % 4,
                }
            )
        )
    return draft.model_copy(update={"placements": updated})
