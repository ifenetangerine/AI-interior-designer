"""Stage 1: CP-SAT feasibility layer with center-based geometry in centimeters."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from ortools.sat.python import cp_model

from colayout.schemas.architecture import resolve_architecture
from colayout.solver.hybrid_types import (
    FurniturePosition,
    HybridFurnitureItem,
    HybridPlacementState,
    HybridSolveConfig,
)

logger = logging.getLogger(__name__)

CM_PER_M = 100
DOOR_CLEARANCE_CM = 120
THETA_STEPS = (0, 90, 180, 270)


@dataclass
class _ItemVars:
    item: HybridFurnitureItem
    cx: cp_model.IntVar
    cz: cp_model.IntVar
    theta_q: cp_model.IntVar
    swap: cp_model.IntVar
    half_x: cp_model.IntVar
    half_z: cp_model.IntVar
    x0: cp_model.IntVar
    x1: cp_model.IntVar
    z0: cp_model.IntVar
    z1: cp_model.IntVar
    x_interval: cp_model.IntervalVar
    z_interval: cp_model.IntervalVar


def _m_to_cm(value_m: float) -> int:
    return int(round(value_m * CM_PER_M))


def _theta_q_from_deg(theta_deg: float) -> int:
    return int(round(theta_deg / 90.0)) % 4


def _half_extents_cm(item: HybridFurnitureItem, swapped: bool) -> tuple[int, int]:
    hw = _m_to_cm(item.dimensions.width_x / 2.0)
    hd = _m_to_cm(item.dimensions.depth_z / 2.0)
    if swapped:
        hw, hd = hd, hw
    return max(1, hw), max(1, hd)


def _build_item_vars(
    model: cp_model.CpModel,
    item: HybridFurnitureItem,
    room_w_cm: int,
    room_l_cm: int,
) -> _ItemVars:
    hw0, hd0 = _half_extents_cm(item, swapped=False)
    max_half = max(hw0, hd0, 1)

    cx = model.NewIntVar(0, room_w_cm, f"cx_{item.id}")
    cz = model.NewIntVar(0, room_l_cm, f"cz_{item.id}")
    theta_q = model.NewIntVar(0, 3, f"theta_{item.id}")
    swap = model.NewBoolVar(f"swap_{item.id}")
    rem = model.NewIntVar(0, 1, f"rem_{item.id}")
    model.AddModuloEquality(rem, theta_q, 2)
    model.Add(swap == rem)

    half_x = model.NewIntVar(1, max_half, f"hx_{item.id}")
    half_z = model.NewIntVar(1, max_half, f"hz_{item.id}")
    model.Add(half_x == hw0).OnlyEnforceIf(swap.Not())
    model.Add(half_z == hd0).OnlyEnforceIf(swap.Not())
    hw1, hd1 = _half_extents_cm(item, swapped=True)
    model.Add(half_x == hw1).OnlyEnforceIf(swap)
    model.Add(half_z == hd1).OnlyEnforceIf(swap)

    x0 = model.NewIntVar(0, room_w_cm, f"x0_{item.id}")
    x1 = model.NewIntVar(0, room_w_cm, f"x1_{item.id}")
    z0 = model.NewIntVar(0, room_l_cm, f"z0_{item.id}")
    z1 = model.NewIntVar(0, room_l_cm, f"z1_{item.id}")
    model.Add(x0 + half_x == cx)
    model.Add(x1 == cx + half_x)
    model.Add(z0 + half_z == cz)
    model.Add(z1 == cz + half_z)

    model.Add(x0 >= 0)
    model.Add(z0 >= 0)
    model.Add(x1 <= room_w_cm)
    model.Add(z1 <= room_l_cm)

    size_x = model.NewIntVar(2, room_w_cm, f"sx_{item.id}")
    size_z = model.NewIntVar(2, room_l_cm, f"sz_{item.id}")
    model.Add(size_x == half_x * 2)
    model.Add(size_z == half_z * 2)

    x_iv = model.NewIntervalVar(x0, size_x, x1, f"xiv_{item.id}")
    z_iv = model.NewIntervalVar(z0, size_z, z1, f"ziv_{item.id}")

    return _ItemVars(
        item=item,
        cx=cx,
        cz=cz,
        theta_q=theta_q,
        swap=swap,
        half_x=half_x,
        half_z=half_z,
        x0=x0,
        x1=x1,
        z0=z0,
        z1=z1,
        x_interval=x_iv,
        z_interval=z_iv,
    )


def _add_door_clearance_constraints(
    model: cp_model.CpModel,
    vars_list: list[_ItemVars],
    state: HybridPlacementState,
    architecture,
) -> None:
    room_w_cm = _m_to_cm(state.width_m)
    room_l_cm = _m_to_cm(state.length_m)
    arch = architecture
    d0 = _m_to_cm(arch.door_offset_m)
    d1 = _m_to_cm(arch.door_offset_m + arch.door_width_m)
    c = DOOR_CLEARANCE_CM

    for iv in vars_list:
        if iv.item.fixed:
            continue
        x0, x1, z0, z1 = iv.x0, iv.x1, iv.z0, iv.z1

        if arch.door_wall == "south":
            overlaps_x = model.NewBoolVar("")
            before = model.NewBoolVar("")
            after = model.NewBoolVar("")
            model.Add(x1 <= d0).OnlyEnforceIf(before)
            model.Add(x1 > d0).OnlyEnforceIf(before.Not())
            model.Add(x0 >= d1).OnlyEnforceIf(after)
            model.Add(x0 < d1).OnlyEnforceIf(after.Not())
            model.AddBoolAnd([before.Not(), after.Not()]).OnlyEnforceIf(overlaps_x)
            model.AddBoolOr([before, after]).OnlyEnforceIf(overlaps_x.Not())
            model.Add(z1 <= c).OnlyEnforceIf(overlaps_x)
        elif arch.door_wall == "north":
            overlaps_x = model.NewBoolVar("")
            before = model.NewBoolVar("")
            after = model.NewBoolVar("")
            model.Add(x1 <= d0).OnlyEnforceIf(before)
            model.Add(x1 > d0).OnlyEnforceIf(before.Not())
            model.Add(x0 >= d1).OnlyEnforceIf(after)
            model.Add(x0 < d1).OnlyEnforceIf(after.Not())
            model.AddBoolAnd([before.Not(), after.Not()]).OnlyEnforceIf(overlaps_x)
            model.AddBoolOr([before, after]).OnlyEnforceIf(overlaps_x.Not())
            model.Add(z0 >= room_l_cm - c).OnlyEnforceIf(overlaps_x)
        elif arch.door_wall == "west":
            overlaps_z = model.NewBoolVar("")
            before = model.NewBoolVar("")
            after = model.NewBoolVar("")
            model.Add(z1 <= d0).OnlyEnforceIf(before)
            model.Add(z1 > d0).OnlyEnforceIf(before.Not())
            model.Add(z0 >= d1).OnlyEnforceIf(after)
            model.Add(z0 < d1).OnlyEnforceIf(after.Not())
            model.AddBoolAnd([before.Not(), after.Not()]).OnlyEnforceIf(overlaps_z)
            model.AddBoolOr([before, after]).OnlyEnforceIf(overlaps_z.Not())
            model.Add(x1 <= c).OnlyEnforceIf(overlaps_z)
        elif arch.door_wall == "east":
            overlaps_z = model.NewBoolVar("")
            before = model.NewBoolVar("")
            after = model.NewBoolVar("")
            model.Add(z1 <= d0).OnlyEnforceIf(before)
            model.Add(z1 > d0).OnlyEnforceIf(before.Not())
            model.Add(z0 >= d1).OnlyEnforceIf(after)
            model.Add(z0 < d1).OnlyEnforceIf(after.Not())
            model.AddBoolAnd([before.Not(), after.Not()]).OnlyEnforceIf(overlaps_z)
            model.AddBoolOr([before, after]).OnlyEnforceIf(overlaps_z.Not())
            model.Add(x0 >= room_w_cm - c).OnlyEnforceIf(overlaps_z)


def _link_stack_children(
    model: cp_model.CpModel,
    vars_by_id: dict[str, _ItemVars],
    state: HybridPlacementState,
) -> None:
    for item in state.items:
        if not item.stack_parent_id:
            continue
        parent = vars_by_id.get(item.stack_parent_id)
        child = vars_by_id.get(item.id)
        if not parent or not child:
            continue
        model.Add(child.cx == parent.cx)
        model.Add(child.cz == parent.cz)
        model.Add(child.theta_q == parent.theta_q)


def solve_stage1_feasibility(
    state: HybridPlacementState,
    config: HybridSolveConfig | None = None,
) -> dict[str, FurniturePosition] | None:
    """Return feasible center positions in meters, or None if infeasible."""
    config = config or HybridSolveConfig()
    free_items = [i for i in state.items if not i.fixed]
    if not free_items:
        return {i.id: i.initial_position for i in state.items}

    room_w_cm = _m_to_cm(state.width_m)
    room_l_cm = _m_to_cm(state.length_m)
    arch = resolve_architecture(
        state.room_type, state.width_m, state.length_m, state.architecture
    )

    model = cp_model.CpModel()
    vars_list = [
        _build_item_vars(model, item, room_w_cm, room_l_cm) for item in free_items
    ]
    vars_by_id = {iv.item.id: iv for iv in vars_list}
    _link_stack_children(model, vars_by_id, state)

    x_intervals = [iv.x_interval for iv in vars_list]
    z_intervals = [iv.z_interval for iv in vars_list]
    if len(x_intervals) > 1:
        model.AddNoOverlap2D(x_intervals, z_intervals)

    _add_door_clearance_constraints(model, vars_list, state, arch)

    hint_penalty: list[cp_model.IntVar] = []
    for iv in vars_list:
        init = iv.item.initial_position
        model.AddHint(iv.cx, _m_to_cm(init.x))
        model.AddHint(iv.cz, _m_to_cm(init.z))
        model.AddHint(iv.theta_q, _theta_q_from_deg(init.theta_deg))

        dx = model.NewIntVar(0, room_w_cm, f"hdx_{iv.item.id}")
        dz = model.NewIntVar(0, room_l_cm, f"hdz_{iv.item.id}")
        model.AddAbsEquality(dx, iv.cx - _m_to_cm(init.x))
        model.AddAbsEquality(dz, iv.cz - _m_to_cm(init.z))
        hint_penalty.extend([dx, dz])

    if hint_penalty:
        model.Minimize(sum(hint_penalty))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.time_limit_s
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.error("Stage 1 CP-SAT status: %s", solver.StatusName(status))
        return None

    positions: dict[str, FurniturePosition] = {}
    for iv in vars_list:
        theta_q = solver.Value(iv.theta_q)
        positions[iv.item.id] = FurniturePosition(
            x=solver.Value(iv.cx) / CM_PER_M,
            z=solver.Value(iv.cz) / CM_PER_M,
            theta_deg=float(THETA_STEPS[theta_q % 4]),
        )

    for item in state.items:
        if item.fixed and item.stack_parent_id:
            parent_pos = positions.get(item.stack_parent_id)
            if parent_pos:
                positions[item.id] = parent_pos.model_copy()
            else:
                positions[item.id] = item.initial_position
        elif item.id not in positions:
            positions[item.id] = item.initial_position

    return positions
