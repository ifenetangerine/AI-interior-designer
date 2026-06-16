"""Full pipeline orchestrator: spatial planning (stages 1–3) + CP-SAT (stage 4)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import (
    draft_to_scene_graph,
    placement_result_from_draft,
)
from colayout.llm.validate_placement import validate_layout_draft
from colayout.pipeline.bundle import RoomPlacementBundle
from colayout.placement.orient import apply_facing_orientations
from colayout.placement_mode import is_llm_only_mode, resolve_placement_mode
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.solver.coarse_to_fine import solve_room_coarse_to_fine
from colayout.solver.hybrid_pipeline import solve_hybrid_placement
from colayout.solver.hybrid_types import HybridSolveConfig

if TYPE_CHECKING:
    from colayout.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


def _llm_generation_warnings(llm: LLMProvider) -> list[str]:
    raw = getattr(llm, "last_generation_warnings", None)
    return list(raw) if raw else []


class LayoutOrchestrator:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def run(
        self,
        room: RoomSpec,
        *,
        modulor_cell_m: float,
        placement_mode: str | None = None,
        coarse_scale: int = 2,
        time_limit_s: float = 30.0,
    ) -> RoomPlacementBundle | None:
        mode = resolve_placement_mode(placement_mode)
        if is_llm_only_mode(placement_mode):
            return self._run_llm_only(room, modulor_cell_m)
        if mode == "llm_refine":
            return self._run_llm_refine(room, modulor_cell_m, time_limit_s)
        return self._run_ip_full(room, modulor_cell_m, coarse_scale, time_limit_s)

    def _generate_draft(self, room: RoomSpec) -> RoomLayoutDraft:
        return self._llm.generate_layout_draft(room)

    def _collect_warnings(self, val_errors: list[str]) -> list[str]:
        warnings = _llm_generation_warnings(self._llm) + list(val_errors)
        spatial = getattr(self._llm, "_spatial", None)
        if spatial and getattr(spatial, "last_warnings", None):
            warnings.extend(spatial.last_warnings)
        return warnings

    def _run_llm_only(
        self,
        room: RoomSpec,
        modulor_cell_m: float,
    ) -> RoomPlacementBundle | None:
        draft = self._generate_draft(room)
        draft, val_errors = validate_layout_draft(draft, room)
        warnings = self._collect_warnings(val_errors)
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

    def _run_llm_refine(
        self,
        room: RoomSpec,
        modulor_cell_m: float,
        time_limit_s: float,
    ) -> RoomPlacementBundle | None:
        draft = self._generate_draft(room)
        draft, val_errors = validate_layout_draft(draft, room)
        warnings = self._collect_warnings(val_errors)

        grid = discretize_room(room, modulor_cell_m)
        graph = draft_to_scene_graph(draft, room)
        llm_placement = apply_facing_orientations(
            placement_result_from_draft(draft, grid), graph
        )

        refine_limit = min(time_limit_s, 15.0)
        hybrid_config = HybridSolveConfig(time_limit_s=refine_limit)
        placement = solve_hybrid_placement(
            draft, room, graph, grid, hybrid_config
        )
        if placement is None:
            logger.warning(
                "Room %s hybrid refine failed; using LLM draft placement", room.id
            )
            warnings.append(
                "(warning) Hybrid refine failed; showing LLM draft positions"
            )
            placement = llm_placement
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

    def _run_ip_full(
        self,
        room: RoomSpec,
        modulor_cell_m: float,
        coarse_scale: int,
        time_limit_s: float,
    ) -> RoomPlacementBundle | None:
        draft = self._generate_draft(room)
        draft, val_errors = validate_layout_draft(draft, room)
        warnings = self._collect_warnings(val_errors)

        grid = discretize_room(room, modulor_cell_m)
        graph = draft_to_scene_graph(draft, room, refine_mode=False)
        placement = solve_room_coarse_to_fine(
            graph,
            grid,
            coarse_scale=coarse_scale,
            time_limit_s=time_limit_s,
        )
        if placement is None:
            return None
        placement = apply_facing_orientations(placement, graph)
        return RoomPlacementBundle(
            placement=placement,
            scene_graph=graph,
            layout_draft=draft,
            warnings=warnings or None,
        )
