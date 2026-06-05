from pydantic import BaseModel, Field

from colayout.schemas.architecture import RoomArchitecture


class PipelineRunRequest(BaseModel):
    room_id: str = "room_1"
    type: str = "bedroom"
    width_m: float = Field(gt=0, default=4.0)
    length_m: float = Field(gt=0, default=3.5)
    preferences: str = ""
    architecture: RoomArchitecture | None = None
    mock_llm: bool = False
    placement_mode: str | None = Field(
        default=None,
        description="Override PLACEMENT_MODE: llm_refine | llm_only | ip_full",
    )
    modulor_cell_m: float = Field(gt=0, default=0.25)
    coarse_scale: int = Field(default=2, ge=1)
    solver_time_limit_s: float = Field(default=30.0, gt=0)


class PipelineRunResponse(BaseModel):
    status: str
    scene_graph: dict
    layout: dict
    placements: list[dict]
    layout_draft: dict | None = None
    placement_mode: str = "llm_refine"
    errors: list[str] = Field(default_factory=list)
