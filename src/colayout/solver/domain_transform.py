"""Coordinate transforms between grid CP-SAT and continuous Stage-2 domains.

Room frame
----------
Origin at the SW corner of the floor footprint.  +X points east, +Z points north
(see ``colayout.placement.orient``).

Grid domain (Stage 1 / CP-SAT)
------------------------------
* ``origin_i``, ``origin_j`` — integer cell indices of the axis-aligned bounding
  box minimum corner (south-west of the footprint in grid space).
* ``centroid_i``, ``centroid_j`` — fractional cell coordinates of the footprint
  center.  The IP solver stores centroids internally at ×100 integer precision
  and exports them as float cell units.
* ``orientation`` — discrete index 0–3 (90° steps).  The grid solver initially
  emits 0|1 via a rotation boolean; ``apply_facing_orientations`` may later set
  0–3 for Kenney mesh alignment.
* Meters from grid centroids::

      x_m = centroid_i * modulor_cell_m
      z_m = centroid_j * modulor_cell_m

Continuous domain (Stage 2 / SciPy)
-----------------------------------
* ``(x, z)`` — footprint center in meters.
* ``theta_rad`` — yaw in the optimization vector ``X``.  Stage-2 sightline and
  wall costs use a simplified 2D proxy forward vector ``f = [cos θ, sin θ]``.
  Kenney catalog meshes may use a different yaw offset per orientation index
  (see ``colayout.assets.orientation.yaw_deg_for_placement``); when converting
  from grid to continuous we optionally apply that catalog yaw so Stage-2 starts
  near the rendered facing direction.
"""

from __future__ import annotations

import math

from colayout.assets.kenney import load_kenney_catalog
from colayout.assets.orientation import yaw_deg_for_placement
from colayout.grid.discretize import GridSpec, meters_to_cells
from colayout.ip.constraints import stack_relation_map
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult, StackMode
from colayout.schemas.scene import RoomSceneGraph
from colayout.solver.hybrid_types import (
    FurniturePosition,
    HybridFurnitureItem,
    HybridPlacementState,
)


def grid_centroid_to_meters(ci: float, cj: float, cell_m: float) -> tuple[float, float]:
    """Convert fractional grid centroid to room-frame meters."""
    return ci * cell_m, cj * cell_m


def meters_to_grid_centroid(x_m: float, z_m: float, cell_m: float) -> tuple[float, float]:
    """Convert room-frame meters to fractional grid centroid."""
    return x_m / cell_m, z_m / cell_m


def orientation_to_theta_deg(
    orientation: int,
    model_id: str | None,
    category: str | None,
    catalog: dict | None = None,
) -> float:
    """Map discrete grid orientation to continuous yaw in degrees."""
    catalog = catalog or load_kenney_catalog()
    return yaw_deg_for_placement(
        catalog,
        model_id or "",
        category or "misc",
        orientation % 4,
    )


def theta_deg_to_orientation(theta_deg: float) -> int:
    """Snap continuous yaw to nearest 90° orientation index."""
    return int(round(theta_deg / 90.0)) % 4


def _half_extents_m(item: HybridFurnitureItem, theta_deg: float) -> tuple[float, float]:
    w, d = item.dimensions.width_x, item.dimensions.depth_z
    if int(round(theta_deg / 90.0)) % 2 == 1:
        w, d = d, w
    return w / 2.0, d / 2.0


def placement_to_furniture_positions(
    placement: RoomPlacementResult,
    grid: GridSpec,
    *,
    use_catalog_yaw: bool = True,
    catalog: dict | None = None,
) -> dict[str, FurniturePosition]:
    """Convert Stage-1 ``RoomPlacementResult`` to continuous Stage-2 positions."""
    cell = grid.modulor_cell_m
    catalog = catalog or load_kenney_catalog()
    out: dict[str, FurniturePosition] = {}
    for f in placement.furniture:
        x, z = grid_centroid_to_meters(f.centroid_i, f.centroid_j, cell)
        if use_catalog_yaw:
            theta_deg = orientation_to_theta_deg(
                f.orientation, f.model_id, f.category, catalog
            )
        else:
            theta_deg = float(f.orientation * 90.0)
        out[f.id] = FurniturePosition(x=x, z=z, theta_deg=theta_deg % 360.0)
    return out


def furniture_positions_to_placement(
    state: HybridPlacementState,
    positions: dict[str, FurniturePosition],
    grid: GridSpec,
    graph: RoomSceneGraph,
    stage1: RoomPlacementResult | None = None,
) -> RoomPlacementResult:
    """Convert continuous Stage-2 positions back to grid ``RoomPlacementResult``."""
    w_grid, l_grid = grid.width_cells, grid.length_cells
    cell = grid.modulor_cell_m
    cell_map: list[list[str | None]] = [[None] * l_grid for _ in range(w_grid)]
    placed: list[PlacedFurniture] = []
    stack_relations = stack_relation_map(graph.constraints)
    stage1_stack: dict[str, tuple[str | None, StackMode | None]] = {}
    if stage1 is not None:
        stage1_stack = {
            f.id: (f.stack_parent_id, f.stack_mode) for f in stage1.furniture
        }

    for item in state.items:
        pos = positions.get(item.id, item.initial_position)
        hw, hd = _half_extents_m(item, pos.theta_deg)
        ox = int(round((pos.x - hw) / cell))
        oz = int(round((pos.z - hd) / cell))
        wc = meters_to_cells(item.dimensions.width_x, cell)
        lc = meters_to_cells(item.dimensions.depth_z, cell)
        orientation = theta_deg_to_orientation(pos.theta_deg)
        if orientation in (1, 3):
            wc, lc = lc, wc
        ox = max(0, min(ox, w_grid - wc))
        oz = max(0, min(oz, l_grid - lc))
        ci, cj = ox + wc / 2.0, oz + lc / 2.0

        if item.id in stage1_stack:
            parent_id, stack_mode = stage1_stack[item.id]
        elif item.id in stack_relations:
            parent_id, stack_mode = stack_relations[item.id]  # type: ignore[assignment]
        else:
            parent_id, stack_mode = None, None

        if item.id not in stack_relations:
            for i in range(ox, ox + wc):
                for j in range(oz, oz + lc):
                    if 0 <= i < w_grid and 0 <= j < l_grid:
                        cell_map[i][j] = item.id

        placed.append(
            PlacedFurniture(
                id=item.id,
                category=item.category or item.item_type,
                model_id=item.model_id,
                origin_i=ox,
                origin_j=oz,
                width_cells=wc,
                length_cells=lc,
                orientation=orientation,
                width_m=item.dimensions.width_x,
                length_m=item.dimensions.depth_z,
                centroid_i=ci,
                centroid_j=cj,
                stack_parent_id=parent_id,
                stack_mode=stack_mode,
            )
        )

    by_id = {f.id: f for f in placed}
    for f in placed:
        if (
            f.stack_mode in ("on_top", "under")
            and f.stack_parent_id
            and f.stack_parent_id in by_id
        ):
            parent = by_id[f.stack_parent_id]
            f.origin_i = parent.origin_i
            f.origin_j = parent.origin_j
            f.centroid_i = parent.centroid_i
            f.centroid_j = parent.centroid_j
            f.orientation = parent.orientation

    return RoomPlacementResult(
        room_id=graph.room_id,
        room_type=graph.room_type,
        grid_w=w_grid,
        grid_l=l_grid,
        modulor_cell_m=cell,
        width_m=grid.width_m,
        length_m=grid.length_m,
        furniture=placed,
        cell_map=cell_map,
    )
