"""Hard front-clearance zones for storage, appliances, and focal pieces."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.ip.constraints import floor_occupancy_exempt_ids, stack_relation_map
from colayout.placement.category_constraints import (
    blocker_allowed_in_front_clearance,
    front_clearance_cells,
    front_clearance_global_exempt,
)
from colayout.schemas.scene import ConstraintType, RoomSceneGraph


def _stack_parent_ids(constraints) -> dict[str, str]:
    return {
        child: parent
        for child, (parent, _mode) in stack_relation_map(constraints).items()
    }


def _wall_by_furniture(graph: RoomSceneGraph) -> dict[str, str]:
    return {
        c.furniture: c.wall
        for c in graph.constraints
        if c.type == ConstraintType.AGAINST_WALL and c.furniture and c.wall
    }


def _should_skip_blocker(
    anchor,
    blocker,
    *,
    stack_parents: dict[str, str],
    floor_exempt: set[str],
) -> bool:
    if anchor.item_id == blocker.item_id:
        return True
    if stack_parents.get(blocker.item_id) == anchor.item_id:
        return True
    if blocker.item_id in floor_exempt:
        return True
    if front_clearance_global_exempt(blocker.category):
        return True
    if blocker_allowed_in_front_clearance(blocker.category, anchor.category):
        return True
    return False


def _rect_non_overlap_separators(
    model: cp_model.CpModel,
    blocker,
    *,
    zone_i0,
    zone_i1,
    zone_j0,
    zone_j1,
) -> list:
    sep_west = model.NewBoolVar("")
    sep_east = model.NewBoolVar("")
    sep_south = model.NewBoolVar("")
    sep_north = model.NewBoolVar("")

    model.Add(blocker.end_x <= zone_i0).OnlyEnforceIf(sep_west)
    model.Add(blocker.end_x > zone_i0).OnlyEnforceIf(sep_west.Not())

    model.Add(blocker.ox >= zone_i1).OnlyEnforceIf(sep_east)
    model.Add(blocker.ox < zone_i1).OnlyEnforceIf(sep_east.Not())

    model.Add(blocker.end_y <= zone_j0).OnlyEnforceIf(sep_south)
    model.Add(blocker.end_y > zone_j0).OnlyEnforceIf(sep_south.Not())

    model.Add(blocker.oy >= zone_j1).OnlyEnforceIf(sep_north)
    model.Add(blocker.oy < zone_j1).OnlyEnforceIf(sep_north.Not())

    return [sep_west, sep_east, sep_south, sep_north]


def _forbid_rect_overlap(
    model: cp_model.CpModel,
    blocker,
    *,
    zone_i0,
    zone_i1,
    zone_j0,
    zone_j1,
    only_enforce_if: cp_model.IntVar | None = None,
) -> None:
    seps = _rect_non_overlap_separators(
        model,
        blocker,
        zone_i0=zone_i0,
        zone_i1=zone_i1,
        zone_j0=zone_j0,
        zone_j1=zone_j1,
    )
    if only_enforce_if is None:
        model.AddBoolOr(seps)
    else:
        model.AddBoolOr(seps).OnlyEnforceIf(only_enforce_if)


def _forbid_wall_front_zone(
    model: cp_model.CpModel,
    anchor,
    blocker,
    wall: str,
    clearance_cells: int,
) -> None:
    """Front zone from against-wall semantics (front faces into room)."""
    if wall == "north":
        _forbid_rect_overlap(
            model,
            blocker,
            zone_i0=anchor.ox,
            zone_i1=anchor.end_x,
            zone_j0=anchor.oy - clearance_cells,
            zone_j1=anchor.oy,
        )
    elif wall == "south":
        _forbid_rect_overlap(
            model,
            blocker,
            zone_i0=anchor.ox,
            zone_i1=anchor.end_x,
            zone_j0=anchor.end_y,
            zone_j1=anchor.end_y + clearance_cells,
        )
    elif wall == "west":
        _forbid_rect_overlap(
            model,
            blocker,
            zone_i0=anchor.end_x,
            zone_i1=anchor.end_x + clearance_cells,
            zone_j0=anchor.oy,
            zone_j1=anchor.end_y,
        )
    elif wall == "east":
        _forbid_rect_overlap(
            model,
            blocker,
            zone_i0=anchor.ox - clearance_cells,
            zone_i1=anchor.ox,
            zone_j0=anchor.oy,
            zone_j1=anchor.end_y,
        )


def _forbid_zone_overlap_rot0(
    model: cp_model.CpModel,
    anchor,
    blocker,
    clearance_cells: int,
) -> None:
    """Blocker must not overlap anchor front zone when rot=0 (front faces +i)."""
    _forbid_rect_overlap(
        model,
        blocker,
        zone_i0=anchor.end_x,
        zone_i1=anchor.end_x + clearance_cells,
        zone_j0=anchor.oy,
        zone_j1=anchor.end_y,
        only_enforce_if=anchor.rot.Not(),
    )


def _forbid_zone_overlap_rot1(
    model: cp_model.CpModel,
    anchor,
    blocker,
    clearance_cells: int,
) -> None:
    """Blocker must not overlap anchor front zone when rot=1 (front faces +j)."""
    _forbid_rect_overlap(
        model,
        blocker,
        zone_i0=anchor.ox,
        zone_i1=anchor.end_x,
        zone_j0=anchor.end_y,
        zone_j1=anchor.end_y + clearance_cells,
        only_enforce_if=anchor.rot,
    )


def add_front_clearance_constraints(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    cell_m: float,
) -> None:
    """Forbid floor furniture from overlapping configured front-clearance zones."""
    floor_exempt = floor_occupancy_exempt_ids(graph.constraints)
    stack_parents = _stack_parent_ids(graph.constraints)
    wall_by_id = _wall_by_furniture(graph)

    for anchor in fv_list:
        if anchor.item_id in floor_exempt:
            continue
        clearance_cells = front_clearance_cells(anchor.category, cell_m)
        if clearance_cells is None:
            continue
        wall = wall_by_id.get(anchor.item_id)

        for blocker in fv_list:
            if _should_skip_blocker(
                anchor,
                blocker,
                stack_parents=stack_parents,
                floor_exempt=floor_exempt,
            ):
                continue

            if wall and wall != "any":
                _forbid_wall_front_zone(
                    model, anchor, blocker, wall, clearance_cells
                )
            else:
                _forbid_zone_overlap_rot0(model, anchor, blocker, clearance_cells)
                _forbid_zone_overlap_rot1(model, anchor, blocker, clearance_cells)
