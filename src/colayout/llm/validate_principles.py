"""Soft validators for classical interior design principles."""

from __future__ import annotations

import math

from colayout.catalog.kenney_index import footprint_for_model, role_for_model
from colayout.design.principle_registry import (
    BALANCE_TOLERANCE,
    COFFEE_SOFA_MAX_M,
    COFFEE_SOFA_MIN_M,
)
from colayout.llm.anchor_structure import (
    check_anchor_structure,
    check_orphan_placements,
    check_relative_position_sanity,
)
from colayout.llm.room_program import anchor_category, constraint_referenced_ids
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft
from colayout.schemas.scene import FurnitureItem, FurnitureConstraint


def _footprint_area(model_id: str) -> float:
    w, d = footprint_for_model(model_id)
    return w * d


def check_lateral_balance(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> str | None:
    mid_x = room.width_m / 2
    left = 0.0
    right = 0.0
    for p in placements:
        area = _footprint_area(p.model_id)
        if p.center_x_m < mid_x - 0.05:
            left += area
        elif p.center_x_m > mid_x + 0.05:
            right += area
    total = left + right
    if total < 0.5:
        return None
    ratio = abs(left - right) / total
    if ratio > BALANCE_TOLERANCE:
        return (
            f"(warning) balance: lateral mass imbalance {ratio:.0%} "
            f"(left {left:.1f} m² vs right {right:.1f} m²)"
        )
    return None


def check_sofa_coffee_proportion(
    placements: list[FurniturePlacementDraft],
) -> str | None:
    sofas = [p for p in placements if role_for_model(p.model_id) == "sofa"]
    tables = [p for p in placements if role_for_model(p.model_id) == "coffee_table"]
    if not sofas or not tables:
        return None
    sofa, coffee = sofas[0], tables[0]
    dist = math.hypot(
        coffee.center_x_m - sofa.center_x_m,
        coffee.center_z_m - sofa.center_z_m,
    )
    if dist < COFFEE_SOFA_MIN_M or dist > COFFEE_SOFA_MAX_M + 0.25:
        return (
            f"(warning) proportion: coffee table {dist:.2f} m from sofa "
            f"(target {COFFEE_SOFA_MIN_M:.2f}–{COFFEE_SOFA_MAX_M:.2f} m)"
        )
    return None


def check_rhythm_spacing(
    placements: list[FurniturePlacementDraft],
) -> str | None:
    by_role: dict[str, list[float]] = {}
    for p in placements:
        role = role_for_model(p.model_id)
        if role in ("nightstand", "lamp", "side_table"):
            by_role.setdefault(role, []).append(p.center_x_m + p.center_z_m)
    for role, coords in by_role.items():
        if len(coords) < 2:
            continue
        coords.sort()
        gaps = [coords[i + 1] - coords[i] for i in range(len(coords) - 1)]
        if len(gaps) >= 2 and max(gaps) - min(gaps) > 0.6:
            return (
                f"(warning) rhythm: uneven spacing between {role} pieces "
                f"(gaps {[round(g, 2) for g in gaps]})"
            )
    return None


def check_structure_connectivity(
    furniture: list[FurnitureItem],
    constraints: list[FurnitureConstraint],
    room_type: str,
) -> str | None:
    anchor = anchor_category(room_type)
    anchor_ids = {f.id for f in furniture if f.category == anchor}
    if not anchor_ids:
        return None
    refs = constraint_referenced_ids(constraints)
    orphans = [
        f.id
        for f in furniture
        if f.id not in refs
        and f.id not in anchor_ids
        and role_for_model(f.model_id or "") not in ("rug", "lamp", "plant", "decor")
    ]
    if orphans:
        return (
            f"(warning) structure: pieces weakly linked to anchor: "
            f"{', '.join(orphans[:3])}"
        )
    return None


def validate_design_principles(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
    furniture: list[FurnitureItem] | None = None,
    constraints: list[FurnitureConstraint] | None = None,
) -> list[str]:
    warnings: list[str] = []
    for fn in (
        lambda: check_anchor_structure(placements, room),
        lambda: check_orphan_placements(placements, room),
        lambda: check_relative_position_sanity(placements),
        lambda: check_lateral_balance(placements, room),
        lambda: check_sofa_coffee_proportion(placements),
        lambda: check_rhythm_spacing(placements),
    ):
        msg = fn()
        if msg:
            warnings.append(msg)
    if furniture and constraints:
        msg = check_structure_connectivity(furniture, constraints, room.type)
        if msg:
            warnings.append(msg)
    return warnings
