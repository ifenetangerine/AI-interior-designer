"""Layout feature vectors for preference reward modeling."""

from __future__ import annotations

import math

from colayout.design.principle_registry import COFFEE_SOFA_MAX_M, COFFEE_SOFA_MIN_M
from colayout.llm.room_program import anchor_category
from colayout.schemas.floor import RoomSpec
from colayout.schemas.placement import RoomPlacementResult
from colayout.schemas.scene import ConstraintType, RoomSceneGraph

FEATURE_NAMES: list[str] = [
    "sofa_coffee_dist_m",
    "sofa_tv_dist_m",
    "chair_desk_dist_m",
    "coffee_proportion_violation",
    "symmetry_residual_m",
    "door_clearance_m",
    "lateral_imbalance_m",
    "orphan_count",
    "wall_dist_bed_m",
    "wall_dist_sofa_m",
    "wall_dist_tv_m",
    "adjacent_gap_violation_m",
    "on_surface_align_m",
    "wall_inset_violation_sleep_m",
    "wall_inset_violation_seating_m",
    "wall_inset_violation_storage_m",
]


def _by_id(placement: RoomPlacementResult) -> dict:
    return {f.id: f for f in placement.furniture}


def _by_cat(placement: RoomPlacementResult) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in placement.furniture:
        cat = f.category or ""
        out.setdefault(cat, []).append(f)
    return out


def _dist_m(a, b) -> float:
    di = (a.centroid_i - b.centroid_i) * 0.01
    dj = (a.centroid_j - b.centroid_j) * 0.01
    return math.hypot(di, dj)


def _wall_dist_m(item, room: RoomSpec) -> float:
    xi = item.centroid_i * 0.01
    zj = item.centroid_j * 0.01
    return min(xi, room.width_m - xi, zj, room.length_m - zj)


def extract_features(
    placement: RoomPlacementResult,
    graph: RoomSceneGraph,
    room: RoomSpec,
) -> dict[str, float]:
    by_id = _by_id(placement)
    by_cat = _by_cat(placement)
    feats: dict[str, float] = {name: 0.0 for name in FEATURE_NAMES}

    sofas = by_cat.get("sofa", [])
    coffees = by_cat.get("coffee_table", [])
    tvs = by_cat.get("tv", []) + by_cat.get("tv_stand", [])
    chairs = by_cat.get("chair", [])
    desks = by_cat.get("desk", [])

    metrics = graph.theta_metrics
    coffee_target = (
        metrics.sofa_coffee_dist_m
        if metrics and metrics.sofa_coffee_dist_m is not None
        else (COFFEE_SOFA_MIN_M + COFFEE_SOFA_MAX_M) / 2
    )
    coffee_band = 0.05

    if sofas and coffees:
        d = _dist_m(sofas[0], coffees[0])
        feats["sofa_coffee_dist_m"] = d
        if d < coffee_target - coffee_band:
            feats["coffee_proportion_violation"] = coffee_target - coffee_band - d
        elif d > coffee_target + coffee_band:
            feats["coffee_proportion_violation"] = d - coffee_target - coffee_band

    if sofas and tvs:
        feats["sofa_tv_dist_m"] = _dist_m(sofas[0], tvs[0])

    if chairs and desks:
        feats["chair_desk_dist_m"] = _dist_m(chairs[0], desks[0])

    sym_residuals: list[float] = []
    for c in graph.constraints:
        if c.type != ConstraintType.SYMMETRIC_PAIR:
            continue
        fa = by_id.get(c.furniture_a or "")
        fb = by_id.get(c.furniture_b or "")
        anchor = by_id.get(c.furniture or "")
        if not fa or not fb or not anchor:
            continue
        if c.axis == "i":
            mirror_i = 2 * anchor.centroid_i - fa.centroid_i
            sym_residuals.append(abs(fb.centroid_i - mirror_i) * 0.01)
        else:
            mirror_j = 2 * anchor.centroid_j - fa.centroid_j
            sym_residuals.append(abs(fb.centroid_j - mirror_j) * 0.01)
    if sym_residuals:
        feats["symmetry_residual_m"] = sum(sym_residuals) / len(sym_residuals)

    arch = graph.architecture
    if arch and arch.door_wall:
        door_center = arch.door_offset_m + arch.door_width_m / 2
        min_clear = 999.0
        for f in placement.furniture:
            xi = f.centroid_i * 0.01
            zj = f.centroid_j * 0.01
            if arch.door_wall == "south":
                along = xi
                clear = zj
            elif arch.door_wall == "north":
                along = xi
                clear = room.length_m - zj
            elif arch.door_wall == "west":
                along = zj
                clear = xi
            else:
                along = zj
                clear = room.width_m - xi
            if abs(along - door_center) <= arch.door_width_m / 2 + 0.3:
                min_clear = min(min_clear, clear)
        if min_clear < 999:
            feats["door_clearance_m"] = min_clear

    if placement.furniture:
        mid_x = room.width_m / 2
        left_mass = 0.0
        right_mass = 0.0
        for f in placement.furniture:
            x = f.centroid_i * 0.01
            w = f.width_m * f.length_m
            if x < mid_x:
                left_mass += w
            else:
                right_mass += w
        feats["lateral_imbalance_m"] = abs(left_mass - right_mass)

    anchor_cat = anchor_category(room.type)
    anchor_ids = {f.id for f in placement.furniture if f.category == anchor_cat}
    constrained: set[str] = set()
    for c in graph.constraints:
        for fid in (c.furniture, c.furniture_a, c.furniture_b):
            if fid:
                constrained.add(fid)
    orphan_radius = (
        metrics.orphan_radius_m
        if metrics and metrics.orphan_radius_m is not None
        else 2.0
    )
    orphans = 0
    for f in placement.furniture:
        if f.id in anchor_ids or f.id in constrained:
            continue
        anchor_piece = next(
            (x for x in placement.furniture if x.category == anchor_cat), None
        )
        if anchor_piece and _dist_m(f, anchor_piece) > orphan_radius:
            orphans += 1
    feats["orphan_count"] = float(orphans)

    beds = by_cat.get("bed", [])
    if beds:
        feats["wall_dist_bed_m"] = _wall_dist_m(beds[0], room)
    if sofas:
        feats["wall_dist_sofa_m"] = _wall_dist_m(sofas[0], room)
    if tvs:
        feats["wall_dist_tv_m"] = _wall_dist_m(tvs[0], room)

    if metrics:
        target_gap = metrics.adjacent_gap_m
        if target_gap > 0:
            gap_violations: list[float] = []
            for c in graph.constraints:
                if c.type != ConstraintType.ADJACENT or c.hard:
                    continue
                fa = by_id.get(c.furniture_a or "")
                fb = by_id.get(c.furniture_b or "")
                if not fa or not fb:
                    continue
                xi_a = fa.centroid_i * 0.01
                zj_a = fa.centroid_j * 0.01
                xi_b = fb.centroid_i * 0.01
                zj_b = fb.centroid_j * 0.01
                dist = math.hypot(xi_a - xi_b, zj_a - zj_b)
                gap_violations.append(abs(dist - target_gap))
            if gap_violations:
                feats["adjacent_gap_violation_m"] = sum(gap_violations) / len(
                    gap_violations
                )

        stack_residuals: list[float] = []
        for c in graph.constraints:
            if c.type != ConstraintType.ON_TOP_OF or c.hard:
                continue
            fa = by_id.get(c.furniture_a or "")
            fb = by_id.get(c.furniture_b or "")
            if not fa or not fb:
                continue
            di = (fa.centroid_i - fb.centroid_i) * 0.01
            dj = (fa.centroid_j - fb.centroid_j) * 0.01
            stack_residuals.append(math.hypot(di, dj))
        if stack_residuals:
            feats["on_surface_align_m"] = sum(stack_residuals) / len(stack_residuals)

        def _inset_violation(
            pieces: list, target: float | None
        ) -> float:
            if target is None or not pieces:
                return 0.0
            residuals = [abs(_wall_dist_m(p, room) - target) for p in pieces]
            return sum(residuals) / len(residuals)

        feats["wall_inset_violation_sleep_m"] = _inset_violation(
            beds, metrics.wall_inset_sleep_m
        )
        feats["wall_inset_violation_seating_m"] = _inset_violation(
            sofas + tvs, metrics.wall_inset_seating_m
        )
        storage_cats = by_cat.get("dresser", []) + by_cat.get("bookshelf", [])
        storage_cats += by_cat.get("fridge", []) + by_cat.get("wardrobe", [])
        feats["wall_inset_violation_storage_m"] = _inset_violation(
            storage_cats, metrics.wall_inset_storage_m
        )

    return feats


def features_vector(features: dict[str, float]) -> list[float]:
    return [features.get(name, 0.0) for name in FEATURE_NAMES]
