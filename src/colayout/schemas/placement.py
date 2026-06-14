from typing import Literal

from pydantic import BaseModel, Field

StackMode = Literal["on_top", "under"]


class PlacedFurniture(BaseModel):
    id: str
    category: str
    model_id: str | None = None
    origin_i: int
    origin_j: int
    width_cells: int
    length_cells: int
    orientation: int = Field(ge=0, le=3)
    width_m: float
    length_m: float
    centroid_i: float
    centroid_j: float
    stack_parent_id: str | None = None
    stack_mode: StackMode | None = None


class RoomPlacementResult(BaseModel):
    room_id: str
    room_type: str
    grid_w: int
    grid_l: int
    modulor_cell_m: float
    width_m: float
    length_m: float
    furniture: list[PlacedFurniture]
    cell_map: list[list[str | None]]


class FloorPlacementResult(BaseModel):
    modulor_cell_m: float
    rooms: list[RoomPlacementResult]
