"""Rigid cluster CP-SAT variables: one master (cluster_x, cluster_z) per compound group."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from colayout.grid.discretize import GridSpec, furniture_cells
from colayout.ip.constraints import floor_occupancy_exempt_ids
from colayout.ip.furniture_vars import FurnitureVars
from colayout.schemas.compound import CompoundGroupPlan
from colayout.schemas.scene import RoomSceneGraph


@dataclass
class ClusterVars:
    """Master placement variables for a rigid compound_group (grid i/j axes)."""

    group_id: str
    cluster_x: cp_model.IntVar  # room i-axis origin of cluster anchor (bbox min)
    cluster_z: cp_model.IntVar  # room j-axis origin of cluster anchor (bbox min)
    bbox_width_cells: int
    bbox_length_cells: int


def member_group_map(
    compound_groups: list[CompoundGroupPlan],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for plan in compound_groups:
        for member in plan.members:
            out[member.item_id] = plan.group_id
    return out


def build_cluster_vars(
    model: cp_model.CpModel,
    compound_groups: list[CompoundGroupPlan],
    w_grid: int,
    l_grid: int,
) -> dict[str, ClusterVars]:
    """Declare exactly ONE cluster_x and ONE cluster_z IntVar per compound group."""
    cluster_vars: dict[str, ClusterVars] = {}
    for plan in compound_groups:
        cx = model.NewIntVar(0, w_grid, f"cluster_x_{plan.group_id}")
        cz = model.NewIntVar(0, l_grid, f"cluster_z_{plan.group_id}")
        model.Add(cx + plan.bbox_width_cells <= w_grid)
        model.Add(cz + plan.bbox_length_cells <= l_grid)
        cluster_vars[plan.group_id] = ClusterVars(
            group_id=plan.group_id,
            cluster_x=cx,
            cluster_z=cz,
            bbox_width_cells=plan.bbox_width_cells,
            bbox_length_cells=plan.bbox_length_cells,
        )
    return cluster_vars


def build_cluster_member_vars(
    model: cp_model.CpModel,
    item,
    member,
    cluster: ClusterVars,
    grid: GridSpec,
    w_grid: int,
    l_grid: int,
) -> FurnitureVars:
    """Child asset vars derived ONLY from cluster master + fixed blueprint offsets.

    ox/oy exist as auxiliary IntVars for NewIntervalVar, but are not independent
    decision variables — each is pinned to cluster_x/z + local constant offset.
    """
    wc, lc = member.width_cells, member.length_cells
    width_m = wc * grid.modulor_cell_m
    length_m = lc * grid.modulor_cell_m
    rot_val = 1 if member.orientation in (1, 3) else 0

    ox = model.NewIntVar(0, w_grid, f"ox_{item.id}")
    oy = model.NewIntVar(0, l_grid, f"oy_{item.id}")
    model.Add(ox == cluster.cluster_x + member.local_ox_cells)
    model.Add(oy == cluster.cluster_z + member.local_oy_cells)

    rot = model.NewBoolVar(f"rot_{item.id}")
    model.Add(rot == rot_val)

    size_x = model.NewIntVar(1, w_grid, f"sx_{item.id}")
    size_y = model.NewIntVar(1, l_grid, f"sy_{item.id}")
    model.Add(size_x == (lc if rot_val else wc))
    model.Add(size_y == (wc if rot_val else lc))

    end_x = model.NewIntVar(0, w_grid, f"ex_{item.id}")
    end_y = model.NewIntVar(0, l_grid, f"ey_{item.id}")
    model.Add(end_x == ox + size_x)
    model.Add(end_y == oy + size_y)
    model.Add(end_x <= w_grid)
    model.Add(end_y <= l_grid)

    x_iv = model.NewIntervalVar(ox, size_x, end_x, f"xiv_{item.id}")
    y_iv = model.NewIntervalVar(oy, size_y, end_y, f"yiv_{item.id}")

    ci = model.NewIntVar(0, w_grid * 100, f"ci_{item.id}")
    cj = model.NewIntVar(0, l_grid * 100, f"cj_{item.id}")
    model.Add(ci * 2 == (ox + end_x) * 100)
    model.Add(cj * 2 == (oy + end_y) * 100)

    return FurnitureVars(
        item_id=item.id,
        category=member.category or "misc",
        model_id=member.model_id,
        width_m=width_m,
        length_m=length_m,
        wc=wc,
        lc=lc,
        ox=ox,
        oy=oy,
        rot=rot,
        size_x=size_x,
        size_y=size_y,
        end_x=end_x,
        end_y=end_y,
        x_interval=x_iv,
        y_interval=y_iv,
        centroid_i=ci,
        centroid_j=cj,
    )


def build_standalone_item_vars(
    model: cp_model.CpModel,
    item,
    grid: GridSpec,
    w_grid: int,
    l_grid: int,
) -> FurnitureVars:
    """Standalone asset: independent ox/oy decision variables (flat path)."""
    wc, lc = furniture_cells(item, grid.modulor_cell_m)
    width_m = item.width_m or 1.0
    length_m = item.length_m or 1.0
    category = item.category or "misc"
    model_id = item.model_id

    ox = model.NewIntVar(0, w_grid, f"ox_{item.id}")
    oy = model.NewIntVar(0, l_grid, f"oy_{item.id}")
    rot = model.NewBoolVar(f"rot_{item.id}")

    size_x = model.NewIntVar(1, w_grid, f"sx_{item.id}")
    size_y = model.NewIntVar(1, l_grid, f"sy_{item.id}")
    model.Add(size_x == wc).OnlyEnforceIf(rot.Not())
    model.Add(size_x == lc).OnlyEnforceIf(rot)
    model.Add(size_y == lc).OnlyEnforceIf(rot.Not())
    model.Add(size_y == wc).OnlyEnforceIf(rot)

    end_x = model.NewIntVar(0, w_grid, f"ex_{item.id}")
    end_y = model.NewIntVar(0, l_grid, f"ey_{item.id}")
    model.Add(end_x == ox + size_x)
    model.Add(end_y == oy + size_y)
    model.Add(end_x <= w_grid)
    model.Add(end_y <= l_grid)

    x_iv = model.NewIntervalVar(ox, size_x, end_x, f"xiv_{item.id}")
    y_iv = model.NewIntervalVar(oy, size_y, end_y, f"yiv_{item.id}")

    ci = model.NewIntVar(0, w_grid * 100, f"ci_{item.id}")
    cj = model.NewIntVar(0, l_grid * 100, f"cj_{item.id}")
    model.Add(ci * 2 == (ox + end_x) * 100)
    model.Add(cj * 2 == (oy + end_y) * 100)

    return FurnitureVars(
        item_id=item.id,
        category=category,
        model_id=model_id,
        width_m=width_m,
        length_m=length_m,
        wc=wc,
        lc=lc,
        ox=ox,
        oy=oy,
        rot=rot,
        size_x=size_x,
        size_y=size_y,
        end_x=end_x,
        end_y=end_y,
        x_interval=x_iv,
        y_interval=y_iv,
        centroid_i=ci,
        centroid_j=cj,
    )


def collect_floor_overlap_intervals(
    fv_list: list[FurnitureVars],
    graph: RoomSceneGraph,
) -> tuple[list[cp_model.IntervalVar], list[cp_model.IntervalVar]]:
    """NoOverlap2D intervals: every child asset footprint + standalone items.

    Cluster members use derived absolute coordinates (not a coarse group bbox).
    """
    floor_exempt = floor_occupancy_exempt_ids(graph.constraints)
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []

    for fv in fv_list:
        if fv.item_id in floor_exempt:
            continue
        x_intervals.append(fv.x_interval)
        y_intervals.append(fv.y_interval)

    return x_intervals, y_intervals


def cluster_hint_from_members(
    plan: CompoundGroupPlan,
    hints: dict[str, tuple[int, int, int]],
) -> tuple[int, int] | None:
    """Derive master cluster_x/cluster_z hint from any child hint."""
    for member in plan.members:
        hint = hints.get(member.item_id)
        if not hint:
            continue
        ox_h, oy_h, _ = hint
        return (
            ox_h - member.local_ox_cells,
            oy_h - member.local_oy_cells,
        )
    return None


# Backward-compatible aliases
build_group_vars = build_cluster_vars
group_hint_from_members = cluster_hint_from_members
build_furniture_item_vars = build_standalone_item_vars
