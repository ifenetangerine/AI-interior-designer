"""Grid-based furniture placement IP using OR-Tools CP-SAT."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ortools.sat.python import cp_model

from colayout.grid.discretize import MAX_GRID_DIM, GridSpec, furniture_cells
from colayout.ip import constraints as ip_constraints
from colayout.ip import objectives as ip_objectives
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult
from colayout.schemas.scene import RoomSceneGraph

from colayout.ip.constraints import floor_occupancy_exempt_ids, stack_parent_map

logger = logging.getLogger(__name__)

@dataclass
class SolveConfig:
    time_limit_s: float = 30.0
    hints: dict[str, tuple[int, int, int]] | None = None  # id -> (ox, oy, orientation 0|1)
    soft_constraints: bool = False


@dataclass
class _FurnitureVars:
    item_id: str
    category: str
    model_id: str | None
    width_m: float
    length_m: float
    wc: int
    lc: int
    ox: cp_model.IntVar
    oy: cp_model.IntVar
    rot: cp_model.IntVar  # 0 = wc along i, 1 = swapped
    size_x: cp_model.IntVar
    size_y: cp_model.IntVar
    end_x: cp_model.IntVar
    end_y: cp_model.IntVar
    x_interval: cp_model.IntervalVar
    y_interval: cp_model.IntervalVar
    centroid_i: cp_model.IntVar
    centroid_j: cp_model.IntVar


def solve_room_placement(
    graph: RoomSceneGraph,
    grid: GridSpec,
    config: SolveConfig | None = None,
) -> RoomPlacementResult | None:
    config = config or SolveConfig()
    w_grid, l_grid = grid.width_cells, grid.length_cells

    model = cp_model.CpModel()
    fv_list: list[_FurnitureVars] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []
    floor_exempt = floor_occupancy_exempt_ids(graph.constraints)
    parents = stack_parent_map(graph.constraints)

    for item in graph.furniture:
        wc, lc = furniture_cells(item, grid.modulor_cell_m)
        ox = model.NewIntVar(0, w_grid, f"ox_{item.id}")
        oy = model.NewIntVar(0, l_grid, f"oy_{item.id}")
        rot = model.NewBoolVar(f"rot_{item.id}")

        size_x = model.NewIntVar(1, w_grid, f"sx_{item.id}")
        size_y = model.NewIntVar(1, l_grid, f"sy_{item.id}")
        model.Add(size_x == wc).OnlyEnforceIf(rot.Not())
        model.Add(size_x == lc).OnlyEnforceIf(rot)
        model.Add(size_y == lc).OnlyEnforceIf(rot.Not())
        model.Add(size_y == wc).OnlyEnforceIf(rot)

        end_x = model.NewIntVar(0, w_grid, f"ex_{item.id}")
        end_y = model.NewIntVar(0, l_grid, f"ey_{item.id}")
        model.Add(end_x == ox + size_x)
        model.Add(end_y == oy + size_y)
        model.Add(end_x <= w_grid)
        model.Add(end_y <= l_grid)

        x_iv = model.NewIntervalVar(ox, size_x, end_x, f"xiv_{item.id}")
        y_iv = model.NewIntervalVar(oy, size_y, end_y, f"yiv_{item.id}")
        if item.id not in floor_exempt:
            x_intervals.append(x_iv)
            y_intervals.append(y_iv)

        ci = model.NewIntVar(0, w_grid * 100, f"ci_{item.id}")
        cj = model.NewIntVar(0, l_grid * 100, f"cj_{item.id}")
        model.Add(ci * 2 == (ox + end_x) * 100)
        model.Add(cj * 2 == (oy + end_y) * 100)

        fv = _FurnitureVars(
            item_id=item.id,
            category=item.category or "misc",
            model_id=item.model_id,
            width_m=item.width_m or 1.0,
            length_m=item.length_m or 1.0,
            wc=wc,
            lc=lc,
            ox=ox,
            oy=oy,
            rot=rot,
            size_x=size_x,
            size_y=size_y,
            end_x=end_x,
            end_y=end_y,
            x_interval=x_iv,
            y_interval=y_iv,
            centroid_i=ci,
            centroid_j=cj,
        )
        fv_list.append(fv)

    if len(fv_list) > 1:
        model.AddNoOverlap2D(x_intervals, y_intervals)

    ip_constraints.add_semantic_interval(
        model,
        fv_list,
        graph.constraints,
        w_grid,
        l_grid,
        config.soft_constraints,
        grid.modulor_cell_m,
    )

    if config.hints:
        for fv in fv_list:
            hint = config.hints.get(fv.item_id)
            if hint:
                ox_h, oy_h, rot_h = hint
                model.AddHint(fv.ox, ox_h)
                model.AddHint(fv.oy, oy_h)
                model.AddHint(fv.rot, rot_h)

    obj_terms = ip_objectives.build_objective_interval(
        model, fv_list, graph, w_grid, l_grid, grid.modulor_cell_m
    )
    if config.hints and config.soft_constraints:
        for fv in fv_list:
            hint = config.hints.get(fv.item_id)
            if not hint:
                continue
            ox_h, oy_h, _ = hint
            di = model.NewIntVar(0, max(w_grid, l_grid), "")
            dj = model.NewIntVar(0, max(w_grid, l_grid), "")
            model.AddAbsEquality(di, fv.ox - ox_h)
            model.AddAbsEquality(dj, fv.oy - oy_h)
            obj_terms.extend([8 * di, 8 * dj])
    if obj_terms:
        model.Minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.time_limit_s
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.error("Solver status: %s", solver.StatusName(status))
        return None

    return _extract_result(solver, fv_list, graph, grid, parents)


def placement_to_hints(result: RoomPlacementResult) -> dict[str, tuple[int, int, int]]:
    return {
        f.id: (f.origin_i, f.origin_j, 1 if f.orientation in (1, 3) else 0)
        for f in result.furniture
    }


def _extract_result(
    solver: cp_model.CpSolver,
    fv_list: list[_FurnitureVars],
    graph: RoomSceneGraph,
    grid: GridSpec,
    stack_parents: dict[str, str] | None = None,
) -> RoomPlacementResult:
    w_grid, l_grid = grid.width_cells, grid.length_cells
    cell_map: list[list[str | None]] = [[None] * l_grid for _ in range(w_grid)]
    placed: list[PlacedFurniture] = []
    centroids: dict[str, tuple[float, float]] = {}

    for fv in fv_list:
        ox = solver.Value(fv.ox)
        oy = solver.Value(fv.oy)
        sx = solver.Value(fv.size_x)
        sy = solver.Value(fv.size_y)
        rot = solver.Value(fv.rot)
        orientation = 1 if rot else 0
        ci = solver.Value(fv.centroid_i) / 100.0
        cj = solver.Value(fv.centroid_j) / 100.0
        centroids[fv.item_id] = (ci, cj)

        if fv.item_id not in (stack_parents or {}):
            for i in range(ox, ox + sx):
                for j in range(oy, oy + sy):
                    cell_map[i][j] = fv.item_id

    for fv in fv_list:
        ox = solver.Value(fv.ox)
        oy = solver.Value(fv.oy)
        sx = solver.Value(fv.size_x)
        sy = solver.Value(fv.size_y)
        rot = solver.Value(fv.rot)
        orientation = 1 if rot else 0
        ci, cj = centroids[fv.item_id]
        parent_id = (stack_parents or {}).get(fv.item_id)
        if parent_id and parent_id in centroids:
            ci, cj = centroids[parent_id]

        placed.append(
            PlacedFurniture(
                id=fv.item_id,
                category=fv.category,
                model_id=fv.model_id,
                origin_i=ox,
                origin_j=oy,
                width_cells=sx,
                length_cells=sy,
                orientation=orientation,
                width_m=fv.width_m,
                length_m=fv.length_m,
                centroid_i=ci,
                centroid_j=cj,
                stack_parent_id=parent_id,
            )
        )

    return RoomPlacementResult(
        room_id=graph.room_id,
        room_type=graph.room_type,
        grid_w=w_grid,
        grid_l=l_grid,
        modulor_cell_m=grid.modulor_cell_m,
        width_m=grid.width_m,
        length_m=grid.length_m,
        furniture=placed,
        cell_map=cell_map,
    )
