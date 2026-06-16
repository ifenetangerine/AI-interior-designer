"""Two-stage hybrid placement: CP-SAT feasibility + continuous aesthetic refine."""

from __future__ import annotations

import logging

from colayout.grid.discretize import GridSpec
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.schemas.placement import RoomPlacementResult
from colayout.schemas.scene import RoomSceneGraph
from colayout.solver.domain_transform import (
    furniture_positions_to_placement,
    placement_to_furniture_positions,
)
from colayout.solver.hybrid_adapters import draft_to_hybrid_state
from colayout.solver.hybrid_types import FurniturePosition, HybridPlacementState, HybridSolveConfig
from colayout.solver.stage1_solver import solve_stage1_feasibility
from colayout.solver.stage2_refiner import refine_stage2_aesthetic

logger = logging.getLogger(__name__)


def _half_extents_m(item, theta_deg: float) -> tuple[float, float]:
    w, d = item.dimensions.width_x, item.dimensions.depth_z
    if int(round(theta_deg / 90.0)) % 2 == 1:
        w, d = d, w
    return w / 2.0, d / 2.0


def _aabb_overlap_2d(
    ax: float,
    az: float,
    ahw: float,
    ahd: float,
    bx: float,
    bz: float,
    bhw: float,
    bhd: float,
    tol: float = 0.02,
) -> bool:
    return (
        ax - ahw < bx + bhw - tol
        and ax + ahw > bx - bhw + tol
        and az - ahd < bz + bhd - tol
        and az + ahd > bz - bhd + tol
    )


def _floor_items_overlap(
    state: HybridPlacementState,
    positions: dict[str, FurniturePosition],
) -> bool:
    free = [i for i in state.items if not i.fixed]
    for i, a in enumerate(free):
        pa = positions[a.id]
        ahw, ahd = _half_extents_m(a, pa.theta_deg)
        for b in free[i + 1 :]:
            pb = positions[b.id]
            bhw, bhd = _half_extents_m(b, pb.theta_deg)
            if _aabb_overlap_2d(pa.x, pa.z, ahw, ahd, pb.x, pb.z, bhw, bhd):
                return True
    return False


def refine_after_ip(
    stage1: RoomPlacementResult,
    draft: RoomLayoutDraft,
    room: RoomSpec,
    graph: RoomSceneGraph,
    grid: GridSpec,
    config: HybridSolveConfig | None = None,
) -> RoomPlacementResult:
    """Run Stage 2 continuous refinement on a Stage-1 IP placement."""
    config = config or HybridSolveConfig()
    state = draft_to_hybrid_state(draft, room, graph)
    stage1_pos = placement_to_furniture_positions(stage1, grid)

    refined = refine_stage2_aesthetic(state, stage1_pos, config)
    if _floor_items_overlap(state, refined):
        logger.warning(
            "Stage 2 introduced overlap for room %s; reverting to Stage 1 layout",
            room.id,
        )
        refined = stage1_pos

    return furniture_positions_to_placement(state, refined, grid, graph, stage1=stage1)


def solve_hybrid_placement(
    draft: RoomLayoutDraft,
    room: RoomSpec,
    graph: RoomSceneGraph,
    grid: GridSpec,
    config: HybridSolveConfig | None = None,
    stage1: RoomPlacementResult | None = None,
) -> RoomPlacementResult | None:
    """Run Stage 1 (CP-SAT) then Stage 2 (SciPy) and return grid placement.

    When ``stage1`` is provided (e.g. from ``ip/solver``), it is used directly
    and the internal hybrid Stage-1 solver is skipped.
    """
    config = config or HybridSolveConfig()
    state = draft_to_hybrid_state(draft, room, graph)

    if stage1 is not None:
        return refine_after_ip(stage1, draft, room, graph, grid, config)

    stage1_pos = solve_stage1_feasibility(state, config)
    if stage1_pos is None:
        logger.warning("Hybrid Stage 1 infeasible for room %s", room.id)
        return None

    refined = refine_stage2_aesthetic(state, stage1_pos, config)
    if _floor_items_overlap(state, refined):
        logger.warning(
            "Stage 2 introduced overlap for room %s; reverting to Stage 1 layout",
            room.id,
        )
        refined = stage1_pos

    return furniture_positions_to_placement(state, refined, grid, graph)
