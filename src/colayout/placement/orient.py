"""Post-placement orientation: face into room and toward focal pieces."""

from __future__ import annotations

import math

from colayout.assets.orientation import yaw_deg_for_placement
from colayout.assets.kenney import load_kenney_catalog
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult
from colayout.schemas.scene import ConstraintType, RoomSceneGraph

# Room +X = east, +Z = north (from SW corner).
INTO_ROOM: dict[str, tuple[float, float]] = {
    "west": (1.0, 0.0),
    "east": (-1.0, 0.0),
    "south": (0.0, 1.0),
    "north": (0.0, -1.0),
}

TABLE_CATEGORIES = frozenset({"desk", "dining_table", "coffee_table", "counter_bar"})
CHAIR_CATEGORIES = frozenset({"chair", "bar_stool"})
FLANK_FACE_CATEGORIES = frozenset({"nightstand", "side_table"})
WALL_FACE_CATEGORIES = frozenset(
    {
        "sofa",
        "desk",
        "wardrobe",
        "dresser",
        "fridge",
        "counter",
        "tv_stand",
        "sink",
        "stove",
    }
)


def _world_front(
    model_id: str | None,
    category: str,
    orientation: int,
    catalog: dict,
) -> tuple[float, float]:
    """Unit vector in room XZ for mesh forward after placement orientation."""
    mid = model_id or ""
    yaw = math.radians(
        yaw_deg_for_placement(catalog, mid, category, orientation)
    )
    return (-math.sin(yaw), -math.cos(yaw))


def best_orientation(
    model_id: str | None,
    category: str,
    target: tuple[float, float],
    catalog: dict | None = None,
) -> int:
    """Pick orientation 0–3 whose mesh forward best aligns with target direction."""
    catalog = catalog or load_kenney_catalog()
    tx, tz = target
    mag = math.hypot(tx, tz)
    if mag < 1e-6:
        return 0
    tx, tz = tx / mag, tz / mag
    best_o = 0
    best_dot = -2.0
    for o in range(4):
        fx, fz = _world_front(model_id, category, o, catalog)
        dot = fx * tx + fz * tz
        if dot > best_dot:
            best_dot = dot
            best_o = o
    return best_o


def _by_id(placed: list[PlacedFurniture]) -> dict[str, PlacedFurniture]:
    return {f.id: f for f in placed}


def _toward(
    src: PlacedFurniture, dst: PlacedFurniture
) -> tuple[float, float]:
    return (
        dst.centroid_i - src.centroid_i,
        dst.centroid_j - src.centroid_j,
    )


def _bed_wall_for_graph(graph: RoomSceneGraph, bed_id: str) -> str:
    for c in graph.constraints:
        if (
            c.type == ConstraintType.AGAINST_WALL
            and c.furniture == bed_id
            and c.wall
            and c.wall != "any"
        ):
            return c.wall
    return "west"


def apply_facing_orientations(
    placement: RoomPlacementResult,
    graph: RoomSceneGraph,
    catalog: dict | None = None,
) -> RoomPlacementResult:
    """Set each piece's orientation so meshes face away from walls and toward tables."""
    catalog = catalog or load_kenney_catalog()
    by_id = _by_id(placement.furniture)
    updates: dict[str, int] = {}

    for c in graph.constraints:
        if c.type in (ConstraintType.FACING, ConstraintType.IN_FRONT_OF):
            if not c.furniture_a or not c.furniture_b:
                continue
            src = by_id.get(c.furniture_a)
            dst = by_id.get(c.furniture_b)
            if not src or not dst:
                continue
            if src.category in CHAIR_CATEGORIES or dst.category in TABLE_CATEGORIES:
                face_from, face_to = src, dst
            elif dst.category in CHAIR_CATEGORIES:
                face_from, face_to = dst, src
            else:
                face_from, face_to = src, dst
            updates[face_from.id] = best_orientation(
                face_from.model_id,
                face_from.category,
                _toward(face_from, face_to),
                catalog,
            )

        elif c.type == ConstraintType.FLANK:
            if not c.furniture_a or not c.furniture_b:
                continue
            ns = by_id.get(c.furniture_a)
            if not ns or ns.category not in FLANK_FACE_CATEGORIES:
                continue
            bed_wall = _bed_wall_for_graph(graph, c.furniture_b)
            target = INTO_ROOM.get(bed_wall)
            if target:
                updates[ns.id] = best_orientation(
                    ns.model_id, ns.category, target, catalog
                )

        elif c.type == ConstraintType.SEATS_AROUND and c.furniture:
            table = by_id.get(c.furniture)
            if not table:
                continue
            for item in placement.furniture:
                if item.category not in CHAIR_CATEGORIES:
                    continue
                if item.id == table.id:
                    continue
                updates[item.id] = best_orientation(
                    item.model_id,
                    item.category,
                    _toward(item, table),
                    catalog,
                )

    facing_locked: set[str] = set()
    for c in graph.constraints:
        if c.type in (ConstraintType.FACING, ConstraintType.IN_FRONT_OF):
            if c.furniture_a:
                facing_locked.add(c.furniture_a)

    arch = graph.architecture
    if (
        arch
        and arch.focal_center_x_m is not None
        and arch.focal_center_z_m is not None
    ):
        cell_m = placement.modulor_cell_m
        fx = arch.focal_center_x_m
        fz = arch.focal_center_z_m
        for item in placement.furniture:
            if item.id in facing_locked:
                continue
            if item.category not in ("sofa", "tv_stand"):
                continue
            cx = item.centroid_i * cell_m
            cz = item.centroid_j * cell_m
            updates[item.id] = best_orientation(
                item.model_id,
                item.category,
                (fx - cx, fz - cz),
                catalog,
            )

    for c in graph.constraints:
        if c.type != ConstraintType.AGAINST_WALL or not c.furniture or not c.wall:
            continue
        item = by_id.get(c.furniture)
        if not item or item.category == "bed":
            continue
        if item.category not in WALL_FACE_CATEGORIES:
            continue
        target = INTO_ROOM.get(c.wall)
        if target:
            updates[item.id] = best_orientation(
                item.model_id, item.category, target, catalog
            )

    if not updates:
        return placement

    new_furniture: list[PlacedFurniture] = []
    for f in placement.furniture:
        if f.id in updates:
            new_furniture.append(f.model_copy(update={"orientation": updates[f.id]}))
        else:
            new_furniture.append(f)
    return placement.model_copy(update={"furniture": new_furniture})
