"""Editable room architecture: door placement."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WallSide = Literal["north", "south", "east", "west"]


class RoomArchitecture(BaseModel):
    door_wall: WallSide = "south"
    door_offset_m: float = Field(default=0.0, ge=0)
    door_width_m: float = Field(default=0.9, gt=0)


def default_architecture(
    room_type: str,
    width_m: float,
    length_m: float,
) -> RoomArchitecture:
    del room_type  # reserved for future room-specific door defaults
    door_offset = max(0.0, width_m / 2 - 0.45)
    return RoomArchitecture(
        door_wall="south",
        door_offset_m=door_offset,
        door_width_m=0.9,
    )


def resolve_architecture(
    room_type: str,
    width_m: float,
    length_m: float,
    architecture: RoomArchitecture | None,
) -> RoomArchitecture:
    if architecture is None:
        return default_architecture(room_type, width_m, length_m)
    return architecture


def architecture_prompt_lines(arch: RoomArchitecture, width_m: float, length_m: float) -> list[str]:
    del width_m, length_m
    return [
        "Room architecture:",
        f"- Door on {arch.door_wall} wall, offset {arch.door_offset_m:.2f} m from SW corner, "
        f"width {arch.door_width_m:.2f} m",
        "- Keep 90 cm clearance in front of door swing; do not block primary circulation",
    ]
