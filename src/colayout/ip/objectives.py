"""Objective terms for furniture placement IP."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.design.principle_registry import COFFEE_SOFA_MAX_M, COFFEE_SOFA_MIN_M
from colayout.ip.constraints import _offset_to_centi
from colayout.llm.room_program import PULL_OUT_RELATIVE, anchor_category
from colayout.schemas.scene import ConstraintType, RoomSceneGraph

STORAGE_CATS = frozenset(
    {"wardrobe", "dresser", "fridge", "counter", "tv_stand", "bookshelf"}
)


def build_objective_interval(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    w_grid: int,
    l_grid: int,
    cell_m: float = 0.25,
) -> list[cp_model.IntVar]:
    w = graph.weights
    terms: list[cp_model.IntVar] = []
    id_to_cat = {fv.item_id: fv.category for fv in fv_list}

    if w.bal > 0.01 and fv_list:
        mid_i = w_grid * 50
        mid_j = l_grid * 50
        for fv in fv_list:
            di = model.NewIntVar(0, 10000, "")
            dj = model.NewIntVar(0, 10000, "")
            model.AddAbsEquality(di, fv.centroid_i - mid_i)
            model.AddAbsEquality(dj, fv.centroid_j - mid_j)
            terms.append(di)
            terms.append(dj)

    if w.walk > 0 and fv_list:
        for fv in fv_list:
            dist_wall = model.NewIntVar(0, 10000, "")
            dw = model.NewIntVar(0, 10000, "")
            de = model.NewIntVar(0, 10000, "")
            ds = model.NewIntVar(0, 10000, "")
            dn = model.NewIntVar(0, 10000, "")
            model.Add(dw == fv.centroid_i)
            model.Add(de == w_grid * 100 - fv.centroid_i)
            model.Add(ds == fv.centroid_j)
            model.Add(dn == l_grid * 100 - fv.centroid_j)
            model.AddMinEquality(dist_wall, [dw, de, ds, dn])
            center_pen = model.NewIntVar(0, 10000, "")
            model.Add(center_pen + dist_wall * 2 >= w_grid * 50)
            terms.append(center_pen)

    if w.rel > 0:
        for c in graph.constraints:
            if c.type != ConstraintType.RELATIVE_POSITION:
                continue
            fa = next((f for f in fv_list if f.item_id == c.furniture_a), None)
            fb = next((f for f in fv_list if f.item_id == c.furniture_b), None)
            if not fa or not fb:
                continue
            ti = _offset_to_centi(c.offset_i, cell_m)
            tj = _offset_to_centi(c.offset_j, cell_m)
            ei = model.NewIntVar(0, 20000, "")
            ej = model.NewIntVar(0, 20000, "")
            model.AddAbsEquality(ei, fa.centroid_i - fb.centroid_i - ti)
            model.AddAbsEquality(ej, fa.centroid_j - fb.centroid_j - tj)
            terms.append(ei)
            terms.append(ej)

        for from_cat, to_cat, oi, oj in PULL_OUT_RELATIVE:
            fa_list = [f for f in fv_list if id_to_cat.get(f.item_id) == from_cat]
            fb_list = [f for f in fv_list if id_to_cat.get(f.item_id) == to_cat]
            if not fa_list or not fb_list:
                continue
            fa, fb = fa_list[0], fb_list[0]
            ti = _offset_to_centi(oi, cell_m)
            tj = _offset_to_centi(oj, cell_m)
            ei = model.NewIntVar(0, 20000, "")
            ej = model.NewIntVar(0, 20000, "")
            model.AddAbsEquality(ei, fa.centroid_i - fb.centroid_i - ti)
            model.AddAbsEquality(ej, fa.centroid_j - fb.centroid_j - tj)
            terms.append(ei)
            terms.append(ej)

    _add_orphan_penalties(model, fv_list, graph, terms)
    _add_lateral_balance(model, fv_list, w, w_grid, terms)
    _add_proportion_terms(model, fv_list, id_to_cat, w, cell_m, terms)
    _add_rhythm_terms(model, fv_list, graph, w_grid, l_grid, terms)
    _add_door_clearance_penalty(
        model, fv_list, graph, w_grid, l_grid, cell_m, terms
    )

    return terms


def _add_lateral_balance(
    model: cp_model.CpModel,
    fv_list: list,
    w: "ObjectiveWeights",
    w_grid: int,
    terms: list[cp_model.IntVar],
) -> None:
    if w.balance <= 0.01 or not fv_list:
        return
    mid = w_grid * 50
    left_parts: list[cp_model.IntVar] = []
    right_parts: list[cp_model.IntVar] = []
    for fv in fv_list:
        weight = fv.wc * fv.lc
        on_left = model.NewBoolVar("")
        model.Add(fv.centroid_i <= mid).OnlyEnforceIf(on_left)
        model.Add(fv.centroid_i > mid).OnlyEnforceIf(on_left.Not())
        lp = model.NewIntVar(0, weight, "")
        rp = model.NewIntVar(0, weight, "")
        model.Add(lp == weight).OnlyEnforceIf(on_left)
        model.Add(lp == 0).OnlyEnforceIf(on_left.Not())
        model.Add(rp == weight).OnlyEnforceIf(on_left.Not())
        model.Add(rp == 0).OnlyEnforceIf(on_left)
        left_parts.append(lp)
        right_parts.append(rp)
    left_sum = model.NewIntVar(0, 500000, "")
    right_sum = model.NewIntVar(0, 500000, "")
    model.Add(left_sum == sum(left_parts))
    model.Add(right_sum == sum(right_parts))
    imbalance = model.NewIntVar(0, 500000, "")
    model.AddAbsEquality(imbalance, left_sum - right_sum)
    terms.append(int(w.balance * 3) * imbalance)


def _add_proportion_terms(
    model: cp_model.CpModel,
    fv_list: list,
    id_to_cat: dict[str, str],
    w: "ObjectiveWeights",
    cell_m: float,
    terms: list[cp_model.IntVar],
) -> None:
    if w.proportion <= 0.01:
        return
    sofas = [f for f in fv_list if id_to_cat.get(f.item_id) == "sofa"]
    coffees = [f for f in fv_list if id_to_cat.get(f.item_id) == "coffee_table"]
    if not sofas or not coffees:
        return
    sofa, coffee = sofas[0], coffees[0]
    min_d = _offset_to_centi(COFFEE_SOFA_MIN_M, cell_m)
    max_d = _offset_to_centi(COFFEE_SOFA_MAX_M, cell_m)
    diff = model.NewIntVar(-20000, 20000, "")
    model.Add(diff == coffee.centroid_j - sofa.centroid_j)
    abs_d = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(abs_d, diff)
    shortfall = model.NewIntVar(0, 20000, "")
    excess = model.NewIntVar(0, 20000, "")
    model.Add(shortfall >= min_d - abs_d)
    model.Add(excess >= abs_d - max_d)
    terms.append(int(w.proportion * 5) * shortfall)
    terms.append(int(w.proportion * 5) * excess)


def _add_rhythm_terms(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    w_grid: int,
    l_grid: int,
    terms: list[cp_model.IntVar],
) -> None:
    if graph.weights.rhythm <= 0.01:
        return
    wall_pieces = [fv for fv in fv_list if fv.category in STORAGE_CATS]
    if len(wall_pieces) < 2:
        return
    wall_pieces = sorted(wall_pieces, key=lambda f: f.item_id)
    for a, b in zip(wall_pieces, wall_pieces[1:]):
        gap = model.NewIntVar(0, 20000, "")
        model.AddAbsEquality(gap, a.centroid_i - b.centroid_i)
        terms.append(int(graph.weights.rhythm * 2) * gap)


def _add_door_clearance_penalty(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    w_grid: int,
    l_grid: int,
    cell_m: float,
    terms: list[cp_model.IntVar],
) -> None:
    arch = graph.architecture
    if not arch or graph.weights.walk <= 0:
        return
    clearance = _offset_to_centi(0.9, cell_m)
    door_mid = _offset_to_centi(
        arch.door_offset_m + arch.door_width_m / 2, cell_m
    )
    for fv in fv_list:
        if fv.category not in STORAGE_CATS:
            continue
        di = model.NewIntVar(0, 20000, "")
        model.AddAbsEquality(di, fv.centroid_i - door_mid)
        close_x = model.NewBoolVar("")
        model.Add(di <= _offset_to_centi(arch.door_width_m, cell_m)).OnlyEnforceIf(
            close_x
        )
        model.Add(di > _offset_to_centi(arch.door_width_m, cell_m)).OnlyEnforceIf(
            close_x.Not()
        )
        if arch.door_wall == "south":
            pen = model.NewIntVar(0, 20000, "")
            model.Add(pen >= clearance - fv.centroid_j).OnlyEnforceIf(close_x)
            model.Add(pen == 0).OnlyEnforceIf(close_x.Not())
            terms.append(pen)


def _add_orphan_penalties(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    terms: list[cp_model.IntVar],
) -> None:
    anchor_cat = anchor_category(graph.room_type)
    anchor_fv = next((f for f in fv_list if f.category == anchor_cat), None)
    if not anchor_fv:
        return

    constrained_ids: set[str] = set()
    for c in graph.constraints:
        if c.furniture:
            constrained_ids.add(c.furniture)
        if c.furniture_a:
            constrained_ids.add(c.furniture_a)
        if c.furniture_b:
            constrained_ids.add(c.furniture_b)

    for fv in fv_list:
        if fv.item_id in constrained_ids or fv.category == anchor_cat:
            continue
        di = model.NewIntVar(0, 20000, "")
        dj = model.NewIntVar(0, 20000, "")
        model.AddAbsEquality(di, fv.centroid_i - anchor_fv.centroid_i)
        model.AddAbsEquality(dj, fv.centroid_j - anchor_fv.centroid_j)
        terms.append(di)
        terms.append(dj)


def link_centroid(*args, **kwargs) -> None:
    pass


def build_objective(*args, **kwargs) -> list:
    return build_objective_interval(*args, **kwargs)
