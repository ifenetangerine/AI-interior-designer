"""Stage 2: continuous aesthetic refinement via SciPy L-BFGS-B.

Takes a feasible Stage-1 layout (from grid CP-SAT) and micro-adjusts positions
in the continuous domain defined by ``domain_transform``.  The optimization vector
is::

    X = [x_1, z_1, theta_1, x_2, z_2, theta_2, ...]

for all non-fixed (floor-level) items.  Cost terms are documented in
``stage2_costs``; bounds keep items within a wander margin of Stage-1.
"""

from __future__ import annotations

import logging
import math

import numpy as np
from scipy.optimize import minimize

from colayout.solver import stage2_costs
from colayout.solver.hybrid_types import (
    FurniturePosition,
    HybridFurnitureItem,
    HybridPlacementState,
    HybridSolveConfig,
)

logger = logging.getLogger(__name__)


def _pack(
    items: list[HybridFurnitureItem],
    positions: dict[str, FurniturePosition],
) -> np.ndarray:
    vec: list[float] = []
    for item in items:
        pos = positions[item.id]
        vec.extend([pos.x, pos.z, math.radians(pos.theta_deg)])
    return np.array(vec, dtype=float)


def _unpack(
    vec: np.ndarray,
    items: list[HybridFurnitureItem],
) -> dict[str, FurniturePosition]:
    out: dict[str, FurniturePosition] = {}
    idx = 0
    for item in items:
        x, z, theta = vec[idx], vec[idx + 1], vec[idx + 2]
        idx += 3
        out[item.id] = FurniturePosition(
            x=float(x),
            z=float(z),
            theta_deg=float(math.degrees(theta) % 360.0),
        )
    return out


def _build_bounds(
    items: list[HybridFurnitureItem],
    stage1: dict[str, FurniturePosition],
    state: HybridPlacementState,
    config: HybridSolveConfig,
) -> list[tuple[float, float]]:
    margin = config.wander_margin_m
    theta_margin = math.radians(config.theta_wander_deg)
    bounds: list[tuple[float, float]] = []
    for item in items:
        pos = stage1[item.id]
        hw = item.dimensions.width_x / 2.0
        hd = item.dimensions.depth_z / 2.0
        bounds.append(
            (
                max(hw, pos.x - margin),
                min(state.width_m - hw, pos.x + margin),
            )
        )
        bounds.append(
            (
                max(hd, pos.z - margin),
                min(state.length_m - hd, pos.z + margin),
            )
        )
        theta0 = math.radians(pos.theta_deg)
        if (item.category or item.item_type) == "bed":
            bounds.append((theta0, theta0))
        else:
            bounds.append((theta0 - theta_margin, theta0 + theta_margin))
    return bounds


def refine_stage2_aesthetic(
    state: HybridPlacementState,
    stage1_positions: dict[str, FurniturePosition],
    config: HybridSolveConfig | None = None,
) -> dict[str, FurniturePosition]:
    """Continuous refinement from Stage 1 feasible layout."""
    config = config or HybridSolveConfig()
    free_items = [i for i in state.items if not i.fixed]
    if not free_items:
        return stage1_positions

    x0 = _pack(free_items, stage1_positions)
    bounds = _build_bounds(free_items, stage1_positions, state, config)

    def objective(vec: np.ndarray) -> float:
        pos = _unpack(vec, free_items)
        return stage2_costs.total_energy(
            free_items,
            pos,
            stage1_positions,
            state.width_m,
            state.length_m,
            w_overlap=config.w_overlap,
            w_sightline=config.w_sightline,
            w_wall=config.w_wall,
            w_anchor=config.w_anchor,
        )

    result = minimize(
        objective,
        x0,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": config.stage2_maxiter, "ftol": 1e-6},
    )

    if not result.success:
        logger.warning("Stage 2 refinement did not converge: %s", result.message)

    refined = dict(stage1_positions)
    refined.update(_unpack(result.x, free_items))

    for item in state.items:
        if item.fixed and item.stack_parent_id:
            parent = refined.get(item.stack_parent_id)
            if parent:
                refined[item.id] = parent.model_copy()

    return refined
