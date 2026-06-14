"""Hard placement constraints: stacking only. Relations are soft objectives."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.schemas.scene import ConstraintType, FurnitureConstraint


def _offset_to_centi(value_m: float, cell_m: float) -> int:
    return int(round(value_m / cell_m)) * 100


def floor_occupancy_exempt_ids(
    constraints: list[FurnitureConstraint],
) -> set[str]:
    """Pieces that do not occupy floor cells (stacked decor, rugs under tables)."""
    exempt: set[str] = set()
    for c in constraints:
        if c.type in (
            ConstraintType.ON_TOP_OF,
            ConstraintType.UNDER,
            ConstraintType.CENTERED_UNDER,
        ):
            if c.furniture_a:
                exempt.add(c.furniture_a)
    return exempt


def stack_parent_map(
    constraints: list[FurnitureConstraint],
) -> dict[str, str]:
    return {child: parent for child, (parent, _) in stack_relation_map(constraints).items()}


def stack_relation_map(
    constraints: list[FurnitureConstraint],
) -> dict[str, tuple[str, str]]:
    """child_id -> (parent_id, stack_mode)."""
    relations: dict[str, tuple[str, str]] = {}
    for c in constraints:
        if c.type == ConstraintType.ON_TOP_OF and c.furniture_a and c.furniture_b:
            relations[c.furniture_a] = (c.furniture_b, "on_top")
        elif c.type in (ConstraintType.UNDER, ConstraintType.CENTERED_UNDER):
            if c.furniture_a and c.furniture_b:
                relations[c.furniture_a] = (c.furniture_b, "under")
    return relations


def _fv_by_id(fv_list: list, fid: str):
    for fv in fv_list:
        if fv.item_id == fid:
            return fv
    return None


def add_hard_constraints(
    model: cp_model.CpModel,
    fv_list: list,
    constraints: list[FurnitureConstraint],
) -> None:
    """Physics-only hard constraints: stack children on parent origin."""
    for c in constraints:
        if c.type not in (ConstraintType.ON_TOP_OF, ConstraintType.UNDER):
            continue
        child = _fv_by_id(fv_list, c.furniture_a or "")
        parent = _fv_by_id(fv_list, c.furniture_b or "")
        if child and parent:
            model.Add(child.ox == parent.ox)
            model.Add(child.oy == parent.oy)
            model.Add(child.rot == parent.rot)
