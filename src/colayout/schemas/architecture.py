"""Editable room architecture: door placement and focal emphasis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WallSide = Literal["north", "south", "east", "west"]


class RoomArchitecture(BaseModel):
    door_wall: WallSide = "south"
    door_offset_m: float = Field(default=0.0, ge=0)
    door_width_m: float = Field(default=0.9, gt=0)
    focal_wall: WallSide | None = None
    focal_center_x_m: float | None = None
    focal_center_z_m: float | None = None


def default_architecture(
    room_type: str,
    width_m: float,
    length_m: float,
) -> RoomArchitecture:
    focal_wall: WallSide | None = {
        "living_room": "north",
        "bedroom": "west",
        "kitchen": "north",
    }.get(room_type, "north")
    focal_x = width_m / 2
    focal_z = length_m / 2
    if focal_wall == "north":
        focal_z = length_m
    elif focal_wall == "south":
        focal_z = 0.0
    elif focal_wall == "west":
        focal_x = 0.0
    elif focal_wall == "east":
        focal_x = width_m

    door_offset = max(0.0, width_m / 2 - 0.45)
    return RoomArchitecture(
        door_wall="south",
        door_offset_m=door_offset,
        door_width_m=0.9,
        focal_wall=focal_wall,
        focal_center_x_m=focal_x,
        focal_center_z_m=focal_z,
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
    lines = [
        "Room architecture:",
        f"- Door on {arch.door_wall} wall, offset {arch.door_offset_m:.2f} m from SW corner, "
        f"width {arch.door_width_m:.2f} m",
        "- Keep 90 cm clearance in front of door swing; do not block primary circulation",
    ]
    if arch.focal_wall:
        fx = arch.focal_center_x_m if arch.focal_center_x_m is not None else width_m / 2
        fz = arch.focal_center_z_m if arch.focal_center_z_m is not None else length_m / 2
        lines.append(
            f"- Focal emphasis on {arch.focal_wall} wall at ({fx:.2f}, {fz:.2f}) m; "
            "orient main seating toward focal point"
        )
    return lines
