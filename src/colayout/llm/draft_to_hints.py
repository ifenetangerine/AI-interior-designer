"""Convert LLM layout drafts to grid hints and scene graphs."""

from __future__ import annotations

from colayout.catalog.kenney_index import (
    footprint_for_model,
    placement_category,
    role_for_model,
)
from colayout.grid.discretize import GridSpec, furniture_cells, meters_to_cells
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult
from colayout.llm.role_constraints import apply_decor_constraints
from colayout.llm.room_program import (
    WALL_HUG_CATEGORIES,
    apply_living_room_constraints,
    apply_relational_constraints,
    default_wall_for_category,
)
from colayout.schemas.architecture import resolve_architecture
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def footprint_m_for_placement(
    p: FurniturePlacementDraft,
) -> tuple[float, float]:
    w, d = footprint_for_model(p.model_id)
    if p.orientation in (1, 3):
        return d, w
    return w, d


def center_to_origin_cells(
    center_x_m: float,
    center_z_m: float,
    width_m: float,
    length_m: float,
    cell_m: float,
    grid_w: int,
    grid_l: int,
) -> tuple[int, int]:
    ox = int(round((center_x_m - width_m / 2) / cell_m))
    oy = int(round((center_z_m - length_m / 2) / cell_m))
    wc = meters_to_cells(width_m, cell_m)
    lc = meters_to_cells(length_m, cell_m)
    ox = max(0, min(ox, grid_w - wc))
    oy = max(0, min(oy, grid_l - lc))
    return ox, oy


def _resolve_surface_parent(
    p: FurniturePlacementDraft,
    by_id: dict[str, FurniturePlacementDraft],
) -> str | None:
    if p.on_surface_of and p.on_surface_of in by_id:
        return p.on_surface_of
    if not p.relative_to or p.relative_to not in by_id:
        return None
    role = role_for_model(p.model_id)
    if role not in ("lamp", "plant", "rug"):
        return None
    parent = by_id[p.relative_to]
    tol = 0.2
    if (
        abs(p.center_x_m - parent.center_x_m) <= tol
        and abs(p.center_z_m - parent.center_z_m) <= tol
    ):
        return p.relative_to
    return None


def _stack_constraints_from_draft(
    draft: RoomLayoutDraft,
) -> list[FurnitureConstraint]:
    by_id = {p.id: p for p in draft.placements}
    out: list[FurnitureConstraint] = []
    for p in draft.placements:
        parent_id = _resolve_surface_parent(p, by_id)
        if not parent_id:
            continue
        role = role_for_model(p.model_id)
        ctype = (
            ConstraintType.UNDER
            if role == "rug"
            else ConstraintType.ON_TOP_OF
        )
        out.append(
            FurnitureConstraint(
                type=ctype,
                furniture_a=p.id,
                furniture_b=parent_id,
            )
        )
    return out


def draft_to_hints(
    draft: RoomLayoutDraft,
    grid: GridSpec,
) -> dict[str, tuple[int, int, int]]:
    by_id = {p.id: p for p in draft.placements}
    stack_parent: dict[str, str] = {}
    for p in draft.placements:
        parent = _resolve_surface_parent(p, by_id)
        if parent:
            stack_parent[p.id] = parent

    hints: dict[str, tuple[int, int, int]] = {}
    for p in draft.placements:
        if p.id in stack_parent:
            continue
        w_m, l_m = footprint_m_for_placement(p)
        ox, oy = center_to_origin_cells(
            p.center_x_m,
            p.center_z_m,
            w_m,
            l_m,
            grid.modulor_cell_m,
            grid.width_cells,
            grid.length_cells,
        )
        rot = 1 if p.orientation in (1, 3) else 0
        hints[p.id] = (ox, oy, rot)

    for child_id, parent_id in stack_parent.items():
        if parent_id in hints:
            hints[child_id] = hints[parent_id]
        else:
            p = by_id[child_id]
            w_m, l_m = footprint_m_for_placement(p)
            ox, oy = center_to_origin_cells(
                p.center_x_m,
                p.center_z_m,
                w_m,
                l_m,
                grid.modulor_cell_m,
                grid.width_cells,
                grid.length_cells,
            )
            hints[child_id] = (ox, oy, 1 if p.orientation in (1, 3) else 0)
    return hints


def draft_to_scene_graph(
    draft: RoomLayoutDraft,
    room: RoomSpec | None = None,
) -> RoomSceneGraph:
    """Scene graph for IP refine: furniture, walls, and relational pairs."""
    furniture: list[FurnitureItem] = []
    constraints: list[FurnitureConstraint] = []

    for p in sorted(draft.placements, key=lambda x: x.placement_order):
        w, d = footprint_for_model(p.model_id)
        cat = placement_category(p.model_id)
        furniture.append(
            FurnitureItem(
                id=p.id,
                model_id=p.model_id,
                category=cat,
                width_m=w,
                length_m=d,
            )
        )
        wall = default_wall_for_category(cat, draft.room_type)
        if wall and cat in WALL_HUG_CATEGORIES:
            constraints.append(
                FurnitureConstraint(
                    type=ConstraintType.AGAINST_WALL,
                    furniture=p.id,
                    wall=wall,
                )
            )
        elif cat == "bed":
            constraints.append(
                FurnitureConstraint(
                    type=ConstraintType.AGAINST_WALL,
                    furniture=p.id,
                    wall="west",
                )
            )
        elif cat == "sofa":
            constraints.append(
                FurnitureConstraint(
                    type=ConstraintType.AGAINST_WALL,
                    furniture=p.id,
                    wall="south",
                )
            )

    constraints.extend(_stack_constraints_from_draft(draft))

    architecture = None
    if room is not None:
        architecture = resolve_architecture(
            room.type, room.width_m, room.length_m, room.architecture
        )

    graph = RoomSceneGraph(
        room_id=draft.room_id,
        room_type=draft.room_type,
        furniture=furniture,
        constraints=constraints,
        weights=draft.weights,
        architecture=architecture,
    )
    graph = apply_relational_constraints(graph)
    graph = apply_living_room_constraints(graph)
    return apply_decor_constraints(graph)


def placement_result_from_draft(
    draft: RoomLayoutDraft,
    grid: GridSpec,
) -> RoomPlacementResult:
    """Build grid placement from draft without IP (snap LLM centers to cells)."""
    from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult
    hints = draft_to_hints(draft, grid)
    by_id = {p.id: p for p in draft.placements}
    stack_parent = {
        p.id: parent
        for p in draft.placements
        if (parent := _resolve_surface_parent(p, by_id))
    }
    placed: list[PlacedFurniture] = []
    cell_map: list[list[str | None]] = [
        [None] * grid.length_cells for _ in range(grid.width_cells)
    ]

    for p in draft.placements:
        w_m, l_m = footprint_m_for_placement(p)
        item = FurnitureItem(
            id=p.id,
            model_id=p.model_id,
            category=placement_category(p.model_id),
            width_m=footprint_for_model(p.model_id)[0],
            length_m=footprint_for_model(p.model_id)[1],
        )
        wc, lc = furniture_cells(item, grid.modulor_cell_m)
        ox, oy, rot = hints[p.id]
        orientation = rot
        if rot:
            wc, lc = lc, wc
        if p.id not in stack_parent:
            for i in range(ox, min(ox + wc, grid.width_cells)):
                for j in range(oy, min(oy + lc, grid.length_cells)):
                    cell_map[i][j] = p.id
        placed.append(
            PlacedFurniture(
                id=p.id,
                category=item.category or "misc",
                model_id=p.model_id,
                origin_i=ox,
                origin_j=oy,
                width_cells=wc,
                length_cells=lc,
                orientation=orientation,
                width_m=w_m,
                length_m=l_m,
                centroid_i=ox + wc / 2.0,
                centroid_j=oy + lc / 2.0,
                stack_parent_id=stack_parent.get(p.id),
            )
        )

    return RoomPlacementResult(
        room_id=draft.room_id,
        room_type=draft.room_type,
        grid_w=grid.width_cells,
        grid_l=grid.length_cells,
        modulor_cell_m=grid.modulor_cell_m,
        width_m=grid.width_m,
        length_m=grid.length_m,
        furniture=placed,
        cell_map=cell_map,
    )
