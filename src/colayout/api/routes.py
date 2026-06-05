from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from colayout.api.schemas import PipelineRunRequest, PipelineRunResponse
from colayout.assets.kenney import load_kenney_catalog, match_kenney_assets
from colayout.llm.provider import get_llm_provider
from colayout.placement_mode import resolve_placement_mode
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import RoomSpec

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/catalog")
def catalog() -> dict:
    return load_kenney_catalog()


@router.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(req: PipelineRunRequest) -> PipelineRunResponse:
    room = RoomSpec(
        id=req.room_id,
        type=req.type,
        width_m=req.width_m,
        length_m=req.length_m,
        preferences=req.preferences,
        architecture=req.architecture,
    )
    llm = get_llm_provider(use_mock=req.mock_llm)
    try:
        mode = resolve_placement_mode(req.placement_mode)
        bundle = place_room_with_graph(
            room,
            llm,
            req.modulor_cell_m,
            coarse_scale=req.coarse_scale,
            time_limit_s=req.solver_time_limit_s,
            placement_mode=mode,
        )
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    if bundle is None:
        raise HTTPException(
            status_code=422,
            detail="Placement solver could not find a feasible layout",
        )

    kenney_catalog = load_kenney_catalog()
    placements = match_kenney_assets(bundle.placement, kenney_catalog)

    layout_draft = (
        bundle.layout_draft.model_dump() if bundle.layout_draft else None
    )
    errors = list(bundle.warnings or [])
    return PipelineRunResponse(
        status="ok",
        scene_graph=bundle.scene_graph.model_dump(),
        layout=bundle.placement.model_dump(),
        placements=[p.model_dump() for p in placements],
        layout_draft=layout_draft,
        placement_mode=mode,
        errors=errors,
    )
