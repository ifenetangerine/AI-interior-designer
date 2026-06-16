"""Category-pair L1 distance constraints for the grid CP-SAT solver."""

from __future__ import annotations

import math

from ortools.sat.python import cp_model

from colayout.ip.constraints import stack_relation_map
from colayout.placement.category_constraints import (
    distance_bounds_centi,
    has_explicit_pair_bounds,
)
from colayout.preference.theta import load_room_theta
from colayout.schemas.scene import RoomSceneGraph


def _room_diag_m(width_m: float, length_m: float) -> float:
    return math.hypot(width_m, length_m)


def _stack_parent_ids(constraints) -> dict[str, str]:
    return {
        child: parent
        for child, (parent, _mode) in stack_relation_map(constraints).items()
    }


def _should_skip_pair(
    fa,
    fb,
    stack_parents: dict[str, str],
) -> bool:
    if fa.item_id == fb.item_id:
        return True
    if stack_parents.get(fa.item_id) == fb.item_id:
        return True
    if stack_parents.get(fb.item_id) == fa.item_id:
        return True
    return False


def iter_bounded_furniture_pairs(
    fv_list: list,
    graph: RoomSceneGraph,
    cell_m: float,
    *,
    room_width_m: float,
    room_length_m: float,
    theta_overrides: dict[str, float] | None = None,
):
    """Yield (fa, fb, min_centi, max_centi) for YAML-defined category pairs."""
    diag = _room_diag_m(room_width_m, room_length_m)
    if diag <= 0:
        return
    stack_parents = _stack_parent_ids(graph.constraints)
    overrides = theta_overrides
    if overrides is None:
        try:
            overrides = load_room_theta(graph.room_type)
        except Exception:
            overrides = None

    for i, fa in enumerate(fv_list):
        for fb in fv_list[i + 1 :]:
            if _should_skip_pair(fa, fb, stack_parents):
                continue
            if not has_explicit_pair_bounds(fa.category, fb.category):
                continue
            min_c, max_c = distance_bounds_centi(
                fa.category,
                fb.category,
                diag,
                cell_m,
                overrides=overrides,
            )
            yield fa, fb, min_c, max_c


def _l1_distance_var(
    model: cp_model.CpModel,
    fa,
    fb,
) -> cp_model.IntVar:
    abs_i = model.NewIntVar(0, 20000, "")
    abs_j = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(abs_i, fa.centroid_i - fb.centroid_i)
    model.AddAbsEquality(abs_j, fa.centroid_j - fb.centroid_j)
    abs_d = model.NewIntVar(0, 40000, "")
    model.Add(abs_d == abs_i + abs_j)
    return abs_d


def add_category_pair_hard_constraints(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    cell_m: float,
    *,
    room_width_m: float,
    room_length_m: float,
) -> None:
    """Hard L1 centroid distance bands from category_constraints.yaml pairs."""
    for fa, fb, min_c, max_c in iter_bounded_furniture_pairs(
        fv_list,
        graph,
        cell_m,
        room_width_m=room_width_m,
        room_length_m=room_length_m,
    ):
        abs_d = _l1_distance_var(model, fa, fb)
        if min_c > 0:
            model.Add(abs_d >= min_c)
        if max_c < 40000:
            model.Add(abs_d <= max_c)


def add_category_pair_soft_penalties(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    cell_m: float,
    terms: list[cp_model.IntVar],
    *,
    room_width_m: float,
    room_length_m: float,
    weight_scale: float = 5.0,
) -> None:
    """Soft shortfall/excess penalties on YAML category-pair distance bands."""
    w = graph.weights
    base_weight = max(w.proportion, 0.05) * weight_scale
    if base_weight <= 0:
        return

    for fa, fb, min_c, max_c in iter_bounded_furniture_pairs(
        fv_list,
        graph,
        cell_m,
        room_width_m=room_width_m,
        room_length_m=room_length_m,
    ):
        abs_d = _l1_distance_var(model, fa, fb)
        shortfall = model.NewIntVar(0, 40000, "")
        excess = model.NewIntVar(0, 40000, "")
        model.Add(shortfall >= min_c - abs_d)
        model.Add(excess >= abs_d - max_c)
        wt = int(base_weight)
        if wt > 0:
            terms.append(wt * shortfall)
            terms.append(wt * excess)
