from pydantic import BaseModel, Field

from colayout.schemas.architecture import RoomArchitecture


class RoomSpec(BaseModel):
    id: str
    type: str
    width_m: float = Field(gt=0)
    length_m: float = Field(gt=0)
    preferences: str = ""
    architecture: RoomArchitecture | None = None


class FloorPlanInput(BaseModel):
    modulor_cell_m: float = Field(default=0.25, gt=0)
    rooms: list[RoomSpec] = Field(min_length=1)
    coarse_scale: int = Field(default=2, ge=1)
    solver_time_limit_s: float = Field(default=30.0, gt=0)
