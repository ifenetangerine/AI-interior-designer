"""Objective terms for furniture placement IP."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.design.principle_registry import COFFEE_SOFA_MAX_M, COFFEE_SOFA_MIN_M
from colayout.ip.constraints import _offset_to_centi
from colayout.llm.room_program import anchor_category
from colayout.schemas.scene import ConstraintType, RoomSceneGraph, ThetaMetrics

SLEEP_CATS = frozenset({"bed"})
SEATING_CATS = frozenset({"sofa", "tv", "tv_stand", "chair"})
STORAGE_WALL_CATS = frozenset(
    {"wardrobe", "dresser", "fridge", "bookshelf", "storage_cabinet", "counter"}
)


def _metrics(graph: RoomSceneGraph) -> ThetaMetrics:
    return graph.theta_metrics or ThetaMetrics()

# Soft cap: anchor-zone children should stay within ~2 m of their anchor in refine.
MAX_ANCHOR_CHILD_OFFSET_M = 2.0

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

    _add_relation_penalties(
        model, fv_list, graph, w_grid, l_grid, cell_m, terms, rel_scale=w.rel
    )
    _add_anchor_child_cluster_penalties(model, fv_list, graph, cell_m, terms)
    _add_orphan_penalties(model, fv_list, graph, cell_m, terms)
    _add_lateral_balance(model, fv_list, w, w_grid, terms)
    _add_proportion_terms(model, fv_list, id_to_cat, w, graph, cell_m, terms)
    _add_viewing_distance_terms(model, fv_list, id_to_cat, w, graph, cell_m, terms)
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
    graph: RoomSceneGraph,
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
    m = _metrics(graph)
    if m.sofa_coffee_dist_m is not None:
        center = m.sofa_coffee_dist_m
        band = 0.05
        min_d = _offset_to_centi(max(0.1, center - band), cell_m)
        max_d = _offset_to_centi(center + band, cell_m)
    else:
        min_d = _offset_to_centi(COFFEE_SOFA_MIN_M, cell_m)
        max_d = _offset_to_centi(COFFEE_SOFA_MAX_M, cell_m)
    # True 2D (L1) distance, not just the j axis: the pair can approach along
    # either axis depending on which wall the sofa backs.
    abs_i = model.NewIntVar(0, 20000, "")
    abs_j = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(abs_i, coffee.centroid_i - sofa.centroid_i)
    model.AddAbsEquality(abs_j, coffee.centroid_j - sofa.centroid_j)
    abs_d = model.NewIntVar(0, 40000, "")
    model.Add(abs_d == abs_i + abs_j)
    shortfall = model.NewIntVar(0, 40000, "")
    excess = model.NewIntVar(0, 40000, "")
    model.Add(shortfall >= min_d - abs_d)
    model.Add(excess >= abs_d - max_d)
    terms.append(int(w.proportion * 5) * shortfall)
    terms.append(int(w.proportion * 5) * excess)


def _add_viewing_distance_terms(
    model: cp_model.CpModel,
    fv_list: list,
    id_to_cat: dict[str, str],
    w: "ObjectiveWeights",
    graph: RoomSceneGraph,
    cell_m: float,
    terms: list[cp_model.IntVar],
) -> None:
    if w.proportion <= 0.01:
        return
    target_m = (_metrics(graph).sofa_tv_dist_m or 3.0)
    band = 0.5
    min_d = _offset_to_centi(max(1.0, target_m - band), cell_m)
    max_d = _offset_to_centi(target_m + band, cell_m)
    sofas = [f for f in fv_list if id_to_cat.get(f.item_id) == "sofa"]
    tvs = [
        f
        for f in fv_list
        if id_to_cat.get(f.item_id) in ("tv", "tv_stand")
    ]
    if not sofas or not tvs:
        return
    abs_i = model.NewIntVar(0, 20000, "")
    abs_j = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(abs_i, sofas[0].centroid_i - tvs[0].centroid_i)
    model.AddAbsEquality(abs_j, sofas[0].centroid_j - tvs[0].centroid_j)
    abs_d = model.NewIntVar(0, 40000, "")
    model.Add(abs_d == abs_i + abs_j)
    shortfall = model.NewIntVar(0, 40000, "")
    excess = model.NewIntVar(0, 40000, "")
    model.Add(shortfall >= min_d - abs_d)
    model.Add(excess >= abs_d - max_d)
    terms.append(int(w.proportion * 4) * shortfall)
    terms.append(int(w.proportion * 4) * excess)


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
    clearance = _offset_to_centi(_metrics(graph).door_clearance_min_m, cell_m)
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


def _add_anchor_child_cluster_penalties(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    cell_m: float,
    terms: list[cp_model.IntVar],
) -> None:
    """Penalize anchor children drifting beyond the LLM offset band."""
    anchor_roles = {
        anchor_category(graph.room_type),
        "desk",
        "dining_table",
        "sink",
        "counter_bar",
        "bookshelf",
        "tv_stand",
    }
    by_cat: dict[str, str] = {}
    for f in graph.furniture:
        cat = f.category or ""
        if cat in anchor_roles and cat not in by_cat:
            by_cat[cat] = f.id

    # Children governed by an explicit config relation (in_front_of, flank,
    # adjacent, ...) should follow that rule, not the raw LLM draft offset.
    rule_governed: set[str] = set()
    for c in graph.constraints:
        if c.type in (
            ConstraintType.IN_FRONT_OF,
            ConstraintType.FLANK,
            ConstraintType.ADJACENT,
            ConstraintType.SEATS_AROUND,
            ConstraintType.ADJACENT_CHAIN,
        ):
            if c.furniture_a:
                rule_governed.add(c.furniture_a)
            if c.furniture:
                rule_governed.add(c.furniture)

    max_off = _offset_to_centi(MAX_ANCHOR_CHILD_OFFSET_M, cell_m)
    for c in graph.constraints:
        if c.type != ConstraintType.RELATIVE_POSITION:
            continue
        if c.furniture_a not in by_cat.values() or not c.furniture_b:
            continue
        if c.furniture_b in rule_governed:
            continue
        anchor = next(
            (fv for fv in fv_list if fv.item_id == c.furniture_a),
            None,
        )
        child = next(
            (fv for fv in fv_list if fv.item_id == c.furniture_b),
            None,
        )
        if not anchor or not child:
            continue
        ti = _offset_to_centi(c.offset_i, cell_m)
        tj = _offset_to_centi(c.offset_j, cell_m)
        di = model.NewIntVar(0, 20000, "")
        dj = model.NewIntVar(0, 20000, "")
        model.AddAbsEquality(di, child.centroid_i - anchor.centroid_i - ti)
        model.AddAbsEquality(dj, child.centroid_j - anchor.centroid_j - tj)
        # Extra weight vs generic rel — keeps children near symmetric LLM offsets.
        terms.extend([12 * di, 12 * dj])


def _fv(fv_list: list, fid: str | None):
    if not fid:
        return None
    return next((f for f in fv_list if f.item_id == fid), None)


def _pen_abs(
    model: cp_model.CpModel,
    expr,
    terms: list[cp_model.IntVar],
    weight: int,
) -> None:
    if weight <= 0:
        return
    v = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(v, expr)
    terms.append(weight * v)


def _wall_by_furniture(graph: RoomSceneGraph) -> dict[str, str]:
    return {
        c.furniture: c.wall
        for c in graph.constraints
        if c.type == ConstraintType.AGAINST_WALL and c.furniture and c.wall
    }


def _add_relation_penalties(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    w_grid: int,
    l_grid: int,
    cell_m: float,
    terms: list[cp_model.IntVar],
    *,
    rel_scale: float = 1.0,
) -> None:
    """All scene-graph relations as soft penalties (θ sets weight / distance_m)."""
    if rel_scale <= 0:
        return
    metrics = _metrics(graph)
    wall_by_id = _wall_by_furniture(graph)
    default_sym = int(max(metrics.symmetry_strength, 1.0))
    seats_done: set[str] = set()

    for c in graph.constraints:
        w = int(max(c.weight, 1.0) * rel_scale)
        fa = _fv(fv_list, c.furniture_a)
        fb = _fv(fv_list, c.furniture_b)

        if c.type == ConstraintType.SYMMETRIC_PAIR:
            anchor = _fv(fv_list, c.furniture)
            if not anchor or not fa or not fb:
                continue
            weight = int(max(c.weight, default_sym) * rel_scale)
            if (c.axis or "i") == "j":
                _pen_abs(
                    model,
                    2 * anchor.centroid_j - fa.centroid_j - fb.centroid_j,
                    terms,
                    weight,
                )
            else:
                _pen_abs(
                    model,
                    2 * anchor.centroid_i - fa.centroid_i - fb.centroid_i,
                    terms,
                    weight,
                )
        elif c.type == ConstraintType.CENTERED_UNDER and fa and fb:
            _pen_abs(model, fa.centroid_i - fb.centroid_i, terms, w)
            _pen_abs(model, fa.centroid_j - fb.centroid_j, terms, w)
        elif c.type == ConstraintType.RELATIVE_POSITION and fa and fb:
            ti = _offset_to_centi(c.offset_i, cell_m)
            tj = _offset_to_centi(c.offset_j, cell_m)
            _pen_abs(model, fa.centroid_i - fb.centroid_i - ti, terms, w)
            _pen_abs(model, fa.centroid_j - fb.centroid_j - tj, terms, w)
        elif c.type == ConstraintType.FACING and fa and fb:
            _pen_abs(
                model,
                fa.centroid_j - fb.centroid_j + (fa.rot - fb.rot) * 5000,
                terms,
                w,
            )
        elif c.type == ConstraintType.ADJACENT and fa and fb:
            gap_c = _offset_to_centi(metrics.adjacent_gap_m, cell_m)
            _pen_abs(model, fa.end_x - fb.ox - gap_c, terms, w)
            _pen_abs(model, fa.end_y - fb.oy, terms, w)
        elif c.type == ConstraintType.IN_FRONT_OF and fa and fb:
            dist = _offset_to_centi(c.distance_m, cell_m)
            wall = wall_by_id.get(c.furniture_b or "")
            front_expr = {
                "south": fa.centroid_j - fb.centroid_j - dist,
                "north": fa.centroid_j - fb.centroid_j + dist,
                "west": fa.centroid_i - fb.centroid_i - dist,
                "east": fa.centroid_i - fb.centroid_i + dist,
            }.get(wall or "", fa.centroid_j - fb.centroid_j + dist)
            _pen_abs(model, front_expr, terms, w)
            perp = (
                fa.centroid_i - fb.centroid_i
                if wall in ("south", "north", None, "")
                else fa.centroid_j - fb.centroid_j
            )
            _pen_abs(model, perp, terms, w)
        elif c.type == ConstraintType.ON_TOP_OF and fa and fb:
            stack_w = int(max(metrics.on_surface_strength, c.weight, 1.0) * rel_scale)
            _pen_abs(model, fa.ox - fb.ox, terms, stack_w)
            _pen_abs(model, fa.oy - fb.oy, terms, stack_w)
        elif c.type == ConstraintType.AGAINST_WALL:
            fv = _fv(fv_list, c.furniture)
            wall = c.wall
            if not fv or not wall or wall == "any":
                continue
            target = _wall_inset_target_m(fv, metrics)
            target_c = _offset_to_centi(target or 0.0, cell_m)
            dist = model.NewIntVar(0, 20000, "")
            if wall == "west":
                model.Add(dist == fv.centroid_i)
            elif wall == "east":
                model.Add(dist == w_grid * 100 - fv.centroid_i)
            elif wall == "south":
                model.Add(dist == fv.centroid_j)
            else:
                model.Add(dist == l_grid * 100 - fv.centroid_j)
            _pen_abs(model, dist - target_c, terms, w)
        elif c.type == ConstraintType.FLANK and fa and fb and c.side:
            bed_wall = wall_by_id.get(fb.item_id, "west")
            if bed_wall in ("west", "east"):
                half_b, half_a = fb.size_y * 50, fa.size_y * 50
                target = (
                    fb.centroid_j - half_b - half_a
                    if c.side == "left"
                    else fb.centroid_j + half_b + half_a
                )
                _pen_abs(model, fa.centroid_j - target, terms, w)
                _pen_abs(model, fa.ox - fb.ox, terms, w)
            else:
                half_b, half_a = fb.size_x * 50, fa.size_x * 50
                target = (
                    fb.centroid_i - half_b - half_a
                    if c.side == "left"
                    else fb.centroid_i + half_b + half_a
                )
                _pen_abs(model, fa.centroid_i - target, terms, w)
                _pen_abs(model, fa.oy - fb.oy, terms, w)
        elif c.type == ConstraintType.ADJACENT_CHAIN and c.furniture_ids:
            fvs = [_fv(fv_list, fid) for fid in c.furniture_ids]
            if any(x is None for x in fvs):
                continue
            for a, b in zip(fvs, fvs[1:]):
                gap_c = _offset_to_centi(metrics.adjacent_gap_m, cell_m)
                _pen_abs(model, a.end_x - b.ox - gap_c, terms, w)
                _pen_abs(model, a.end_y - b.oy, terms, w)
        elif c.type == ConstraintType.SEATS_AROUND:
            table_id = c.furniture or ""
            if table_id in seats_done:
                continue
            table = _fv(fv_list, table_id)
            if not table:
                continue
            half_ti = table.size_x * 50
            half_tj = table.size_y * 50
            for chair in (f for f in fv_list if f.category == "chair"):
                half_ci = chair.size_x * 50
                half_cj = chair.size_y * 50
                di = model.NewIntVar(0, 20000, "")
                dj = model.NewIntVar(0, 20000, "")
                model.AddAbsEquality(di, chair.centroid_i - table.centroid_i)
                model.AddAbsEquality(dj, chair.centroid_j - table.centroid_j)
                ideal = model.NewIntVar(0, 20000, "")
                model.Add(ideal >= di - half_ti - half_ci)
                model.Add(ideal >= dj - half_tj - half_cj)
                terms.append(w * ideal)
            seats_done.add(table_id)


def _wall_inset_target_m(fv, metrics: ThetaMetrics) -> float | None:
    cat = fv.category or ""
    if cat in SLEEP_CATS and metrics.wall_inset_sleep_m is not None:
        return metrics.wall_inset_sleep_m
    if cat in SEATING_CATS and metrics.wall_inset_seating_m is not None:
        return metrics.wall_inset_seating_m
    if cat in STORAGE_WALL_CATS and metrics.wall_inset_storage_m is not None:
        return metrics.wall_inset_storage_m
    return None


def _add_orphan_penalties(
    model: cp_model.CpModel,
    fv_list: list,
    graph: RoomSceneGraph,
    cell_m: float,
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

    metrics = _metrics(graph)
    orphan_w = int(max(metrics.orphan_weight, 1.0))
    radius_c = _offset_to_centi(metrics.orphan_radius_m, cell_m)

    for fv in fv_list:
        if fv.item_id in constrained_ids or fv.category == anchor_cat:
            continue
        di = model.NewIntVar(0, 20000, "")
        dj = model.NewIntVar(0, 20000, "")
        model.AddAbsEquality(di, fv.centroid_i - anchor_fv.centroid_i)
        model.AddAbsEquality(dj, fv.centroid_j - anchor_fv.centroid_j)
        excess_i = model.NewIntVar(0, 20000, "")
        excess_j = model.NewIntVar(0, 20000, "")
        model.Add(excess_i >= di - radius_c)
        model.Add(excess_j >= dj - radius_c)
        terms.append(orphan_w * excess_i)
        terms.append(orphan_w * excess_j)


