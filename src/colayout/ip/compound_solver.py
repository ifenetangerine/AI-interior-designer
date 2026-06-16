"""Rigid cluster CP-SAT wiring in the main grid solver."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.grid.discretize import GridSpec
from colayout.ip.compound_vars import (
    build_cluster_member_vars,
    build_cluster_vars,
    build_standalone_item_vars,
    collect_floor_overlap_intervals,
    member_group_map,
)
from colayout.ip.furniture_vars import FurnitureVars
from colayout.ip.constraints import floor_occupancy_exempt_ids
from colayout.schemas.scene import RoomSceneGraph


def build_compound_furniture_vars(
    model: cp_model.CpModel,
    graph: RoomSceneGraph,
    grid: GridSpec,
) -> tuple[list[FurnitureVars], list[cp_model.IntervalVar], list[cp_model.IntervalVar]]:
    """Compound path: master cluster_x/z per group; child intervals for collision."""
    w_grid, l_grid = grid.width_cells, grid.length_cells
    compound_groups = graph.compound_groups or []
    fv_list: list[FurnitureVars] = []
    grouped = member_group_map(compound_groups)
    member_by_id = {
        m.item_id: m for p in compound_groups for m in p.members
    }
    cluster_vars = build_cluster_vars(model, compound_groups, w_grid, l_grid)

    for item in graph.furniture:
        member = member_by_id.get(item.id)
        if member is not None:
            fv = build_cluster_member_vars(
                model,
                item,
                member,
                cluster_vars[grouped[item.id]],
                grid,
                w_grid,
                l_grid,
            )
        else:
            fv = build_standalone_item_vars(model, item, grid, w_grid, l_grid)
        fv_list.append(fv)

    x_intervals, y_intervals = collect_floor_overlap_intervals(fv_list, graph)
    return fv_list, x_intervals, y_intervals


def build_flat_furniture_vars(
    model: cp_model.CpModel,
    graph: RoomSceneGraph,
    grid: GridSpec,
) -> tuple[list[FurnitureVars], list[cp_model.IntervalVar], list[cp_model.IntervalVar]]:
    """Original flat loop: independent ox/oy per standalone asset."""
    w_grid, l_grid = grid.width_cells, grid.length_cells
    fv_list: list[FurnitureVars] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []
    floor_exempt = floor_occupancy_exempt_ids(graph.constraints)

    for item in graph.furniture:
        fv = build_standalone_item_vars(model, item, grid, w_grid, l_grid)
        if item.id not in floor_exempt:
            x_intervals.append(fv.x_interval)
            y_intervals.append(fv.y_interval)
        fv_list.append(fv)

    return fv_list, x_intervals, y_intervals
