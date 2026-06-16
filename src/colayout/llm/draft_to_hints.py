"""Convert LLM layout drafts to grid hints and scene graphs."""

from __future__ import annotations

import math

from colayout.catalog.kenney_index import (
    footprint_for_model,
    is_stackable_child_role,
    is_valid_surface_stack,
    placement_category,
    role_for_model,
)
from colayout.grid.discretize import GridSpec, furniture_cells, meters_to_cells
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.placement import (
    PlacedFurniture,
    RoomPlacementResult,
    StackMode,
)
from colayout.llm.room_program import (
    WALL_HUG_CATEGORIES,
    default_wall_for_category,
)
from colayout.schemas.architecture import resolve_architecture
from colayout.schemas.floor import RoomSpec
from colayout.schemas.compound import CompoundGroupPlan
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


def draft_footprint_overlap(
    a: FurniturePlacementDraft,
    b: FurniturePlacementDraft,
    *,
    tol: float = 0.02,
) -> bool:
    aw, al = footprint_m_for_placement(a)
    bw, bl = footprint_m_for_placement(b)
    a_x0, a_x1 = a.center_x_m - aw / 2, a.center_x_m + aw / 2
    a_z0, a_z1 = a.center_z_m - al / 2, a.center_z_m + al / 2
    b_x0, b_x1 = b.center_x_m - bw / 2, b.center_x_m + bw / 2
    b_z0, b_z1 = b.center_z_m - bl / 2, b.center_z_m + bl / 2
    return (
        a_x0 < b_x1 - tol
        and a_x1 > b_x0 + tol
        and a_z0 < b_z1 - tol
        and a_z1 > b_z0 + tol
    )


def _footprint_contains_point(
    parent: FurniturePlacementDraft,
    x: float,
    z: float,
    *,
    tol: float = 0.03,
) -> bool:
    pw, pl = footprint_m_for_placement(parent)
    x0, x1 = parent.center_x_m - pw / 2 - tol, parent.center_x_m + pw / 2 + tol
    z0, z1 = parent.center_z_m - pl / 2 - tol, parent.center_z_m + pl / 2 + tol
    return x0 <= x <= x1 and z0 <= z <= z1


def child_overlaps_parent(
    child: FurniturePlacementDraft,
    parent: FurniturePlacementDraft,
) -> bool:
    """True when child footprint/center still overlaps parent (stack or unstack)."""
    child_role = role_for_model(child.model_id)
    if child_role == "rug":
        return draft_footprint_overlap(child, parent)
    if _footprint_contains_point(parent, child.center_x_m, child.center_z_m):
        return True
    return draft_footprint_overlap(child, parent)


def _find_stack_parent_by_overlap(
    p: FurniturePlacementDraft,
    by_id: dict[str, FurniturePlacementDraft],
) -> str | None:
    """Pick smallest valid surface parent when child overlaps parent footprint."""
    if not is_stackable_child_role(role_for_model(p.model_id)):
        return None
    candidates: list[FurniturePlacementDraft] = []
    for other in by_id.values():
        if other.id == p.id:
            continue
        if not is_valid_surface_stack(p.model_id, other.model_id):
            continue
        if child_overlaps_parent(p, other):
            candidates.append(other)
    if not candidates:
        return None
    candidates.sort(
        key=lambda o: footprint_m_for_placement(o)[0] * footprint_m_for_placement(o)[1]
    )
    return candidates[0].id


def _resolve_surface_parent(
    p: FurniturePlacementDraft,
    by_id: dict[str, FurniturePlacementDraft],
) -> str | None:
    role = role_for_model(p.model_id)
    if role == "tv":
        if p.on_surface_of and p.on_surface_of in by_id:
            parent = by_id[p.on_surface_of]
            if is_valid_surface_stack(p.model_id, parent.model_id):
                return p.on_surface_of
        for other in by_id.values():
            if other.relative_to == p.id and is_valid_surface_stack(
                p.model_id, other.model_id
            ):
                return other.id
    if not is_stackable_child_role(role):
        return None
    if p.on_surface_of and p.on_surface_of in by_id:
        parent = by_id[p.on_surface_of]
        if (
            is_valid_surface_stack(p.model_id, parent.model_id)
            and child_overlaps_parent(p, parent)
        ):
            return p.on_surface_of
    if p.relative_to and p.relative_to in by_id:
        parent = by_id[p.relative_to]
        if is_valid_surface_stack(p.model_id, parent.model_id):
            role = role_for_model(p.model_id)
            if role == "rug" and child_overlaps_parent(p, parent):
                return p.relative_to
            tol = 0.2
            if (
                abs(p.center_x_m - parent.center_x_m) <= tol
                and abs(p.center_z_m - parent.center_z_m) <= tol
            ):
                return p.relative_to
    return _find_stack_parent_by_overlap(p, by_id)


def auto_link_overlapping_stacks(
    placements: list[FurniturePlacementDraft],
) -> list[FurniturePlacementDraft]:
    """Sync on_surface_of from overlap; preserve TV-on-console stacks."""
    by_id = {p.id: p for p in placements}
    out: list[FurniturePlacementDraft] = []
    for p in placements:
        role = role_for_model(p.model_id)
        if role == "tv":
            parent_id = _resolve_surface_parent(p, by_id)
            if parent_id and parent_id in by_id:
                parent = by_id[parent_id]
                out.append(
                    p.model_copy(
                        update={
                            "on_surface_of": parent_id,
                            "center_x_m": round(parent.center_x_m, 3),
                            "center_z_m": round(parent.center_z_m, 3),
                        }
                    )
                )
                continue
        if not is_stackable_child_role(role):
            out.append(p)
            continue
        parent_id = _find_stack_parent_by_overlap(p, by_id)
        if (
            parent_id is None
            and role == "tv"
            and p.on_surface_of
            and p.on_surface_of in by_id
        ):
            parent = by_id[p.on_surface_of]
            if is_valid_surface_stack(p.model_id, parent.model_id):
                out.append(p)
                continue
        if parent_id != p.on_surface_of:
            out.append(p.model_copy(update={"on_surface_of": parent_id}))
        else:
            out.append(p)
    return out


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
            ConstraintType.CENTERED_UNDER
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


_OPPOSITE_WALL = {"north": "south", "south": "north", "east": "west", "west": "east"}


def _sofa_wall_for_draft(
    draft: RoomLayoutDraft,
    room: RoomSpec | None,
) -> str:
    """Sofa backs the wall opposite the TV so seating faces the screen."""
    if room is None:
        return "south"
    # The config rule is the authoritative TV wall (draft TV positions are
    # often unreliable before refine); fall back to draft geometry.
    from colayout.relations.loader import get_rules_for_role, relation_kinds

    kinds = relation_kinds()
    for rule in get_rules_for_role("tv", room.type):
        spec = kinds.get(rule.kind)
        if spec and spec.ip_type == "against_wall" and rule.wall:
            return _OPPOSITE_WALL.get(rule.wall, "south")

    tv = next(
        (
            p
            for p in draft.placements
            if placement_category(p.model_id) in ("tv", "tv_stand")
        ),
        None,
    )
    if tv is None:
        return "south"
    dists = {
        "west": tv.center_x_m,
        "east": room.width_m - tv.center_x_m,
        "south": tv.center_z_m,
        "north": room.length_m - tv.center_z_m,
    }
    tv_wall = min(dists, key=dists.get)
    return _OPPOSITE_WALL[tv_wall]


def draft_to_scene_graph(
    draft: RoomLayoutDraft,
    room: RoomSpec | None = None,
    *,
    refine_mode: bool = True,
    compound_groups: list[CompoundGroupPlan] | None = None,
) -> RoomSceneGraph:
    """Scene graph for IP refine: furniture, walls, and relational pairs."""
    furniture: list[FurnitureItem] = []
    constraints: list[FurnitureConstraint] = []
    sofa_wall = _sofa_wall_for_draft(draft, room)

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
                    hard=cat == "counter" and draft.room_type == "kitchen",
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
                    wall=sofa_wall,
                )
            )

    constraints.extend(_stack_constraints_from_draft(draft))
    if room is not None:
        from colayout.llm.anchor_structure import (
            anchor_relative_constraints,
            anchor_symmetric_pair_constraints,
        )

        constraints.extend(anchor_relative_constraints(draft.placements, room))
        constraints.extend(anchor_symmetric_pair_constraints(draft.placements, room))

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
        compound_groups=list(compound_groups or []),
    )
    if room is not None:
        from colayout.relations.apply import apply_anchor_relation_constraints

        graph = apply_anchor_relation_constraints(
            graph, draft, room, refine_mode=refine_mode
        )
    return graph


def placement_result_from_draft(
    draft: RoomLayoutDraft,
    grid: GridSpec,
    *,
    preserve_centers: bool = False,
) -> RoomPlacementResult:
    """Build grid placement from draft without IP (snap LLM centers to cells)."""
    from colayout.schemas.placement import PlacedFurniture, RoomPlacementResult
    hints = None if preserve_centers else draft_to_hints(draft, grid)
    by_id = {p.id: p for p in draft.placements}
    stack_parent: dict[str, str] = {}
    stack_mode: dict[str, StackMode] = {}
    for p in draft.placements:
        parent = _resolve_surface_parent(p, by_id)
        if not parent:
            continue
        stack_parent[p.id] = parent
        role = role_for_model(p.model_id)
        stack_mode[p.id] = "under" if role == "rug" else "on_top"
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
        orientation = p.orientation
        if preserve_centers:
            if orientation in (1, 3):
                wc, lc = lc, wc
            centroid_i = p.center_x_m / grid.modulor_cell_m
            centroid_j = p.center_z_m / grid.modulor_cell_m
            ox = int(math.floor(centroid_i - wc / 2.0))
            oy = int(math.floor(centroid_j - lc / 2.0))
            ox = max(0, min(ox, grid.width_cells - wc))
            oy = max(0, min(oy, grid.length_cells - lc))
        else:
            ox, oy, rot = hints[p.id]
            if rot:
                wc, lc = lc, wc
            centroid_i = ox + wc / 2.0
            centroid_j = oy + lc / 2.0
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
                centroid_i=centroid_i,
                centroid_j=centroid_j,
                stack_parent_id=stack_parent.get(p.id),
                stack_mode=stack_mode.get(p.id),
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
