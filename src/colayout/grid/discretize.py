import math
from dataclasses import dataclass

from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import FurnitureItem

PREFERRED_CELL_M = 0.25
MAX_GRID_DIM = 48


@dataclass(frozen=True)
class GridSpec:
    width_cells: int
    length_cells: int
    modulor_cell_m: float
    width_m: float
    length_m: float


def meters_to_cells(value_m: float, cell_m: float) -> int:
    return max(1, int(math.ceil(value_m / cell_m)))


def resolve_modulor_cell_m(room: RoomSpec, requested: float | None = None) -> float:
    """Pick cell size: prefer finer cells, coarsen only if grid would exceed MAX_GRID_DIM."""
    cell = requested if requested is not None else PREFERRED_CELL_M
    cell = max(0.1, cell)
    while True:
        w = meters_to_cells(room.width_m, cell)
        l = meters_to_cells(room.length_m, cell)
        if max(w, l) <= MAX_GRID_DIM:
            return round(cell, 4)
        next_cell = cell * 2.0
        if next_cell > 1.0:
            return 1.0
        cell = next_cell


def discretize_room(room: RoomSpec, modulor_cell_m: float | None = None) -> GridSpec:
    cell_m = resolve_modulor_cell_m(room, modulor_cell_m)
    w = meters_to_cells(room.width_m, cell_m)
    l = meters_to_cells(room.length_m, cell_m)
    return GridSpec(
        width_cells=w,
        length_cells=l,
        modulor_cell_m=cell_m,
        width_m=room.width_m,
        length_m=room.length_m,
    )


def furniture_cells(item: FurnitureItem, cell_m: float) -> tuple[int, int]:
    w = item.width_m if item.width_m is not None else 1.0
    l = item.length_m if item.length_m is not None else 1.0
    return (
        meters_to_cells(w, cell_m),
        meters_to_cells(l, cell_m),
    )
