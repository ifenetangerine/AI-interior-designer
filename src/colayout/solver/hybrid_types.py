"""Data structures for the two-stage hybrid placement solver."""

from __future__ import annotations

from pydantic import BaseModel, Field

from colayout.schemas.architecture import RoomArchitecture


class FurnitureDimensions(BaseModel):
    width_x: float = Field(gt=0, description="Footprint extent along room +X (m)")
    depth_z: float = Field(gt=0, description="Footprint extent along room +Z (m)")
    height_y: float = Field(gt=0, default=0.5)


class FurniturePosition(BaseModel):
    x: float = Field(ge=0)
    z: float = Field(ge=0)
    theta_deg: float = Field(ge=0, lt=360, default=0.0)


class HybridFurnitureItem(BaseModel):
    """Single furniture asset for hybrid Stage 1 / Stage 2 optimization."""

    id: str
    dimensions: FurnitureDimensions
    initial_position: FurniturePosition
    item_type: str = Field(
        description="Semantic type, e.g. sofa, tv_stand, wall_anchor, chair"
    )
    model_id: str | None = None
    category: str | None = None
    focal_target_id: str | None = None
    is_wall_anchor: bool = False
    stack_parent_id: str | None = None
    fixed: bool = False


class HybridSolveConfig(BaseModel):
    time_limit_s: float = 15.0
    stage2_maxiter: int = 200
    wander_margin_m: float = 0.45
    theta_wander_deg: float = 45.0
    w_overlap: float = 50.0
    w_sightline: float = 8.0
    w_wall: float = 6.0
    w_anchor: float = 40.0


class HybridPlacementState(BaseModel):
    room_id: str
    room_type: str
    width_m: float
    length_m: float
    items: list[HybridFurnitureItem]
    architecture: RoomArchitecture | None = None
