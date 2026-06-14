from typing import Literal

from pydantic import BaseModel, Field

from colayout.schemas.scene import ObjectiveWeights


class FurniturePlacementDraft(BaseModel):
    id: str
    model_id: str
    placement_order: int = Field(ge=1)
    center_x_m: float = Field(ge=0)
    center_z_m: float = Field(ge=0)
    orientation: int = Field(default=0, ge=0, le=3)
    relative_to: str | None = None
    on_surface_of: str | None = None
    composition_role: Literal["anchor", "support", "accent", "decor"] | None = None
    zone: str | None = None
    note: str | None = None


class RoomLayoutDraft(BaseModel):
    room_id: str
    room_type: str
    placements: list[FurniturePlacementDraft] = Field(min_length=1)
    weights: ObjectiveWeights = Field(
        default_factory=lambda: ObjectiveWeights(rel=0.2, bal=0.0, walk=0.1)
    )
