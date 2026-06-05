from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import (
    draft_to_hints,
    draft_to_scene_graph,
    placement_result_from_draft,
)
from colayout.llm.provider import LLMProvider
from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    validate_layout_draft,
)
from colayout.placement.orient import apply_facing_orientations
from colayout.placement_mode import is_llm_only_mode, resolve_placement_mode
from colayout.schemas.floor import FloorPlanInput, RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.schemas.placement import FloorPlacementResult, RoomPlacementResult
from colayout.schemas.scene import RoomSceneGraph
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine

logger = logging.getLogger(__name__)


@dataclass
class RoomPlacementBundle:
    placement: RoomPlacementResult
    scene_graph: RoomSceneGraph
    layout_draft: RoomLayoutDraft | None = None
    warnings: list[str] | None = None


def place_room_with_graph(
    room: RoomSpec,
    llm: LLMProvider,
    modulor_cell_m: float,
    coarse_scale: int = 2,
    time_limit_s: float = 30.0,
    placement_mode: str | None = None,
) -> RoomPlacementBundle | None:
    mode = resolve_placement_mode(placement_mode)
    if is_llm_only_mode(placement_mode):
        return _place_room_llm_only(room, llm, modulor_cell_m)
    if mode == "llm_refine":
        return _place_room_llm_refine(room, llm, modulor_cell_m, time_limit_s)
    return _place_room_ip_full(room, llm, modulor_cell_m, coarse_scale, time_limit_s)


def _llm_generation_warnings(llm: LLMProvider) -> list[str]:
    raw = getattr(llm, "last_generation_warnings", None)
    return list(raw) if raw else []


def _place_room_llm_only(
    room: RoomSpec,
    llm: LLMProvider,
    modulor_cell_m: float,
) -> RoomPlacementBundle | None:
    draft = llm.generate_layout_draft(room)
    draft, val_errors = validate_layout_draft(draft, room)
    warnings = _llm_generation_warnings(llm) + val_errors
    blocking = [e for e in val_errors if is_blocking_placement_error(e)]
    if blocking:
        logger.warning(
            "Room %s layout draft blocking errors: %s",
            room.id,
            "; ".join(blocking),
        )
        return None
    if val_errors:
        logger.info(
            "Room %s llm_only warnings: %s", room.id, "; ".join(val_errors)
        )
    grid = discretize_room(room, modulor_cell_m)
    graph = draft_to_scene_graph(draft, room)
    placement = apply_facing_orientations(
        placement_result_from_draft(draft, grid), graph
    )
    return RoomPlacementBundle(
        placement=placement,
        scene_graph=graph,
        layout_draft=draft,
        warnings=warnings or None,
    )


def _place_room_llm_refine(
    room: RoomSpec,
    llm: LLMProvider,
    modulor_cell_m: float,
    time_limit_s: float,
) -> RoomPlacementBundle | None:
    draft = llm.generate_layout_draft(room)
    draft, val_errors = validate_layout_draft(draft, room)
    warnings = _llm_generation_warnings(llm) + list(val_errors)
    blocking = [e for e in val_errors if is_blocking_placement_error(e)]
    if blocking:
        logger.warning(
            "Room %s layout draft blocking errors: %s",
            room.id,
            "; ".join(blocking),
        )
        return None

    grid = discretize_room(room, modulor_cell_m)
    hints = draft_to_hints(draft, grid)
    graph = draft_to_scene_graph(draft, room)

    refine_limit = min(time_limit_s, 15.0)
    placement = solve_room_placement(
        graph,
        grid,
        SolveConfig(
            hints=hints,
            soft_constraints=True,
            time_limit_s=refine_limit,
        ),
    )
    if placement is None:
        logger.warning(
            "Room %s refine failed; retrying without hints", room.id
        )
        placement = solve_room_placement(
            graph,
            grid,
            SolveConfig(
                soft_constraints=True,
                time_limit_s=refine_limit,
            ),
        )
    if placement is None:
        logger.warning(
            "Room %s refine failed; using LLM draft placement", room.id
        )
        warnings.append(
            "(warning) IP refine failed; showing LLM draft positions"
        )
        placement = apply_facing_orientations(
            placement_result_from_draft(draft, grid), graph
        )
        return RoomPlacementBundle(
            placement=placement,
            scene_graph=graph,
            layout_draft=draft,
            warnings=warnings or None,
        )

    if val_errors:
        logger.info(
            "Room %s refine warnings: %s", room.id, "; ".join(val_errors)
        )
    placement = apply_facing_orientations(placement, graph)
    return RoomPlacementBundle(
        placement=placement,
        scene_graph=graph,
        layout_draft=draft,
        warnings=warnings or None,
    )


def _place_room_ip_full(
    room: RoomSpec,
    llm: LLMProvider,
    modulor_cell_m: float,
    coarse_scale: int,
    time_limit_s: float,
) -> RoomPlacementBundle | None:
    graph = llm.generate_scene_graph(room)
    grid = discretize_room(room, modulor_cell_m)
    placement = solve_room_coarse_to_fine(
        graph,
        grid,
        coarse_scale=coarse_scale,
        time_limit_s=time_limit_s,
    )
    if placement is None:
        return None
    placement = apply_facing_orientations(placement, graph)
    return RoomPlacementBundle(placement=placement, scene_graph=graph)


def place_room(
    room: RoomSpec,
    llm: LLMProvider,
    modulor_cell_m: float,
    coarse_scale: int = 2,
    time_limit_s: float = 30.0,
) -> RoomPlacementResult | None:
    bundle = place_room_with_graph(
        room, llm, modulor_cell_m, coarse_scale, time_limit_s
    )
    return bundle.placement if bundle else None


@dataclass
class FloorPlacementBundle:
    floor: FloorPlacementResult
    scene_graphs: dict[str, RoomSceneGraph]
    layout_drafts: dict[str, RoomLayoutDraft]


def place_floor_with_graphs(
    floor: FloorPlanInput,
    llm: LLMProvider,
    max_workers: int | None = None,
) -> FloorPlacementBundle:
    workers = max_workers or min(len(floor.rooms), 4)
    results: dict[str, RoomPlacementBundle] = {}

    def _run(r: RoomSpec) -> tuple[str, RoomPlacementBundle | None]:
        bundle = place_room_with_graph(
            r,
            llm,
            floor.modulor_cell_m,
            coarse_scale=floor.coarse_scale,
            time_limit_s=floor.solver_time_limit_s,
        )
        return r.id, bundle

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run, r): r.id for r in floor.rooms}
        for fut in as_completed(futures):
            rid, bundle = fut.result()
            if bundle is None:
                raise RuntimeError(f"Placement failed for room {rid}")
            results[rid] = bundle

    ordered_rooms = [results[r.id].placement for r in floor.rooms if r.id in results]
    scene_graphs = {
        r.id: results[r.id].scene_graph for r in floor.rooms if r.id in results
    }
    layout_drafts = {
        r.id: results[r.id].layout_draft
        for r in floor.rooms
        if r.id in results and results[r.id].layout_draft is not None
    }
    return FloorPlacementBundle(
        floor=FloorPlacementResult(
            modulor_cell_m=floor.modulor_cell_m,
            rooms=ordered_rooms,
        ),
        scene_graphs=scene_graphs,
        layout_drafts=layout_drafts,
    )


def place_floor(
    floor: FloorPlanInput,
    llm: LLMProvider,
    max_workers: int | None = None,
) -> FloorPlacementResult:
    return place_floor_with_graphs(floor, llm, max_workers).floor
