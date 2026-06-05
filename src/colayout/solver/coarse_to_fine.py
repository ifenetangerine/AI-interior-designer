"""Coarse-to-fine furniture placement per room."""

from __future__ import annotations

import logging
import math

from colayout.grid.discretize import GridSpec, furniture_cells
from colayout.ip.solver import SolveConfig, placement_to_hints, solve_room_placement
from colayout.schemas.placement import RoomPlacementResult
from colayout.schemas.scene import FurnitureItem, RoomSceneGraph

logger = logging.getLogger(__name__)


def _scale_graph(graph: RoomSceneGraph, scale: int, cell_m: float) -> RoomSceneGraph:
    scaled_furniture: list[FurnitureItem] = []
    for f in graph.furniture:
        wc, lc = furniture_cells(f, cell_m)
        sw = max(1, math.ceil(wc / scale))
        sl = max(1, math.ceil(lc / scale))
        scaled_furniture.append(
            FurnitureItem(
                id=f.id,
                model_id=f.model_id,
                category=f.category,
                width_m=sw * cell_m * scale,
                length_m=sl * cell_m * scale,
            )
        )
    return graph.model_copy(update={"furniture": scaled_furniture})


def _scale_hints(
    hints: dict[str, tuple[int, int, int]], scale: int
) -> dict[str, tuple[int, int, int]]:
    return {k: (v[0] // scale, v[1] // scale, v[2]) for k, v in hints.items()}


def solve_room_coarse_to_fine(
    graph: RoomSceneGraph,
    grid: GridSpec,
    coarse_scale: int = 2,
    time_limit_s: float = 30.0,
) -> RoomPlacementResult | None:
    if coarse_scale <= 1:
        return solve_room_placement(
            graph, grid, SolveConfig(time_limit_s=time_limit_s)
        )

    coarse_w = max(1, math.ceil(grid.width_cells / coarse_scale))
    coarse_l = max(1, math.ceil(grid.length_cells / coarse_scale))
    coarse_cell_m = grid.modulor_cell_m * coarse_scale

    coarse_grid = GridSpec(
        width_cells=coarse_w,
        length_cells=coarse_l,
        modulor_cell_m=coarse_cell_m,
        width_m=grid.width_m,
        length_m=grid.length_m,
    )
    coarse_graph = _scale_graph(graph, coarse_scale, grid.modulor_cell_m)

    coarse_result = solve_room_placement(
        coarse_graph,
        coarse_grid,
        SolveConfig(time_limit_s=time_limit_s * 0.4, soft_constraints=True),
    )

    hints = None
    if coarse_result:
        hints = _scale_hints(placement_to_hints(coarse_result), coarse_scale)
        logger.info("Coarse phase succeeded for room %s", graph.room_id)
    else:
        logger.warning("Coarse phase failed for room %s; fine-only", graph.room_id)

    fine = solve_room_placement(
        graph,
        grid,
        SolveConfig(
            time_limit_s=time_limit_s,
            hints=hints,
            soft_constraints=False,
        ),
    )
    if fine:
        return fine

    fine = solve_room_placement(
        graph, grid, SolveConfig(time_limit_s=time_limit_s, soft_constraints=True)
    )
    if fine:
        return fine

    return solve_room_placement(
        graph,
        grid,
        SolveConfig(time_limit_s=time_limit_s * 1.5),
    )
