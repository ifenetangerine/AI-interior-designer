"""IP constraints for furniture placement."""

from __future__ import annotations

from ortools.sat.python import cp_model

from colayout.schemas.scene import ConstraintType, FurnitureConstraint

# Cardinal offsets only: chair centered on each table side (offset_i=0 or offset_j=0).
SURROUND_OFFSETS_M: list[tuple[float, float]] = [
    (0.0, -0.75),
    (0.0, 0.75),
    (-0.75, 0.0),
    (0.75, 0.0),
]

TOUCH_TOL = 25
HEADBOARD_CELL_TOL = 1
CENTER_TOL = 55  # half-cell on centroid grid (centi-units)
WALL_INSET_CELLS = 1  # keep grid footprint off room boundary (beds exempt)
# Grid rot for wall-backed pieces (matches snap_placement / bed convention).
WALL_BACKED_ROT: dict[str, int] = {
    "west": 1,
    "east": 1,
    "south": 0,
    "north": 0,
}
FACE_TOWARD_MARGIN = 30  # centi-units on centroid grid

# Seating-zone links stay hard during soft IP refine so the anchor group does not scatter.
REFINE_HARD_ADJACENT_CATS = frozenset(
    {"sofa", "coffee_table", "tv_stand", "side_table", "chair", "rug"}
)


def _adjacent_hard_in_refine(soft: bool, fa, fb) -> bool:
    if not soft:
        return True
    return (
        fa.category in REFINE_HARD_ADJACENT_CATS
        and fb.category in REFINE_HARD_ADJACENT_CATS
    )


def _fv_by_id(fv_list: list, fid: str):
    for fv in fv_list:
        if fv.item_id == fid:
            return fv
    return None


def floor_occupancy_exempt_ids(
    constraints: list[FurnitureConstraint],
) -> set[str]:
    """Pieces that do not occupy floor cells (stacked lamps, rugs under tables)."""
    exempt: set[str] = set()
    for c in constraints:
        if c.type in (ConstraintType.ON_TOP_OF, ConstraintType.UNDER):
            if c.furniture_a:
                exempt.add(c.furniture_a)
    return exempt


def stack_parent_map(
    constraints: list[FurnitureConstraint],
) -> dict[str, str]:
    parents: dict[str, str] = {}
    for c in constraints:
        if c.type in (ConstraintType.ON_TOP_OF, ConstraintType.UNDER):
            if c.furniture_a and c.furniture_b:
                parents[c.furniture_a] = c.furniture_b
    return parents


def _offset_to_centi(value_m: float, cell_m: float) -> int:
    return int(round(value_m / cell_m)) * 100


def _bed_wall_for(
    constraints: list[FurnitureConstraint], bed_id: str
) -> str:
    for c in constraints:
        if (
            c.type == ConstraintType.AGAINST_WALL
            and c.furniture == bed_id
            and c.wall
            and c.wall != "any"
        ):
            return c.wall
    return "west"


def add_semantic_interval(
    model: cp_model.CpModel,
    fv_list: list,
    constraints: list[FurnitureConstraint],
    w_grid: int,
    l_grid: int,
    soft: bool = False,
    cell_m: float = 0.25,
) -> None:
    categories = {fv.item_id: fv.category for fv in fv_list}
    seats_done: set[str] = set()

    for c in constraints:
        if c.type == ConstraintType.AGAINST_WALL:
            fv = _fv_by_id(fv_list, c.furniture or "")
            if fv is None:
                continue
            _against_wall_interval(
                model,
                fv,
                c.wall or "any",
                w_grid,
                l_grid,
                soft,
                categories.get(fv.item_id),
            )
        elif c.type == ConstraintType.ALIGNMENT:
            fa = _fv_by_id(fv_list, c.furniture_a or "")
            fb = _fv_by_id(fv_list, c.furniture_b or "")
            if fa and fb and fa.item_id != fb.item_id:
                model.Add(fa.rot == fb.rot)
        elif c.type == ConstraintType.FACING:
            fa = _fv_by_id(fv_list, c.furniture_a or "")
            fb = _fv_by_id(fv_list, c.furniture_b or "")
            if fa and fb:
                _facing_interval(model, fa, fb)
        elif c.type == ConstraintType.ADJACENT:
            fa = _fv_by_id(fv_list, c.furniture_a or "")
            fb = _fv_by_id(fv_list, c.furniture_b or "")
            if fa and fb:
                hard = _adjacent_hard_in_refine(soft, fa, fb)
                _adjacent_interval(model, fa, fb, hard=hard)
        elif c.type == ConstraintType.RELATIVE_POSITION and not soft:
            fa = _fv_by_id(fv_list, c.furniture_a or "")
            fb = _fv_by_id(fv_list, c.furniture_b or "")
            if fa and fb:
                di = _offset_to_centi(c.offset_i, cell_m)
                dj = _offset_to_centi(c.offset_j, cell_m)
                model.Add(fa.centroid_i + di == fb.centroid_i)
                model.Add(fa.centroid_j + dj == fb.centroid_j)
        elif c.type == ConstraintType.FLANK:
            fa = _fv_by_id(fv_list, c.furniture_a or "")
            fb = _fv_by_id(fv_list, c.furniture_b or "")
            if fa and fb and c.side:
                wall = _bed_wall_for(constraints, fb.item_id)
                _flank_interval(model, fa, fb, c.side, wall)
        elif c.type == ConstraintType.IN_FRONT_OF:
            fa = _fv_by_id(fv_list, c.furniture_a or "")
            fb = _fv_by_id(fv_list, c.furniture_b or "")
            if fa and fb:
                _facing_interval(model, fa, fb)
                _in_front_of_interval(model, fa, fb, c.distance_m, cell_m)
                _touching_adjacent_interval(model, fa, fb)
        elif c.type == ConstraintType.ADJACENT_CHAIN and not soft:
            _adjacent_chain_interval(
                model, fv_list, c.furniture_ids, c.wall or "north", w_grid, l_grid
            )
        elif c.type == ConstraintType.ON_TOP_OF:
            child = _fv_by_id(fv_list, c.furniture_a or "")
            parent = _fv_by_id(fv_list, c.furniture_b or "")
            if child and parent:
                _on_top_of_interval(model, child, parent)
        elif c.type == ConstraintType.UNDER:
            child = _fv_by_id(fv_list, c.furniture_a or "")
            parent = _fv_by_id(fv_list, c.furniture_b or "")
            if child and parent:
                _on_top_of_interval(model, child, parent)
        elif c.type == ConstraintType.SEATS_AROUND:
            table_id = c.furniture or ""
            if table_id in seats_done:
                continue
            table_fv = _fv_by_id(fv_list, table_id)
            if not table_fv:
                continue
            chair_fvs = [
                fv
                for fv in fv_list
                if fv.category == "chair"
                and fv.item_id not in _desk_paired_chair_ids(constraints)
            ]
            _seats_around_interval(
                model, chair_fvs, table_fv, cell_m, hard=not soft
            )
            seats_done.add(table_id)

    has_flank = any(c.type == ConstraintType.FLANK for c in constraints)
    if not soft or has_flank:
        _apply_nightstand_symmetry(model, fv_list, constraints)


def _desk_paired_chair_ids(constraints: list[FurnitureConstraint]) -> set[str]:
    ids: set[str] = set()
    for c in constraints:
        if c.type == ConstraintType.IN_FRONT_OF and c.furniture_a:
            ids.add(c.furniture_a)
    return ids


def _flank_sides_for_bed(
    constraints: list[FurnitureConstraint], bed_id: str
) -> dict[str, str]:
    """Map nightstand id -> left|right from flank constraints."""
    sides: dict[str, str] = {}
    for c in constraints:
        if (
            c.type == ConstraintType.FLANK
            and c.furniture_b == bed_id
            and c.furniture_a
            and c.side
        ):
            sides[c.furniture_a] = c.side
    return sides


def _apply_nightstand_symmetry(
    model: cp_model.CpModel,
    fv_list: list,
    constraints: list[FurnitureConstraint],
) -> None:
    """Mirror two nightstands about the bed centroid on the flank axis."""
    for bed in (fv for fv in fv_list if fv.category == "bed"):
        sides = _flank_sides_for_bed(constraints, bed.item_id)
        if len(sides) != 2:
            continue
        ids = list(sides.keys())
        ns_a = _fv_by_id(fv_list, ids[0])
        ns_b = _fv_by_id(fv_list, ids[1])
        if not ns_a or not ns_b:
            continue
        wall = _bed_wall_for(constraints, bed.item_id)
        if wall in ("west", "east"):
            model.Add(2 * bed.centroid_j == ns_a.centroid_j + ns_b.centroid_j)
        else:
            model.Add(2 * bed.centroid_i == ns_a.centroid_i + ns_b.centroid_i)


def _seats_around_interval(
    model: cp_model.CpModel,
    chair_fvs: list,
    table_fv,
    cell_m: float,
    hard: bool,
) -> None:
    """Chairs on centered cardinal sides of the table."""
    for idx, chair in enumerate(chair_fvs[: len(SURROUND_OFFSETS_M)]):
        oi, oj = SURROUND_OFFSETS_M[idx]
        _facing_interval(model, chair, table_fv)
        if hard:
            di = _offset_to_centi(oi, cell_m)
            dj = _offset_to_centi(oj, cell_m)
            if abs(oi) >= 0.01:
                model.Add(chair.centroid_i + di == table_fv.centroid_i)
            else:
                _centered_on_axis(model, chair.centroid_i, table_fv.centroid_i)
            if abs(oj) >= 0.01:
                model.Add(chair.centroid_j + dj == table_fv.centroid_j)
            else:
                _centered_on_axis(model, chair.centroid_j, table_fv.centroid_j)


def _flank_interval(
    model: cp_model.CpModel,
    ns,
    bed,
    side: str,
    bed_wall: str,
) -> None:
    """Nightstand touching bed, headboard-aligned, on left or right."""
    _touching_bedside(model, ns, bed, side, bed_wall)
    _headboard_align(model, ns, bed, bed_wall)


def _touching_bedside(
    model: cp_model.CpModel,
    ns,
    bed,
    side: str,
    bed_wall: str,
) -> None:
    """Edge-touch along the axis perpendicular to left/right (no gap)."""
    if bed_wall in ("west", "east"):
        half_bed = bed.size_y * 50
        half_ns = ns.size_y * 50
        if side == "left":
            model.Add(ns.centroid_j + half_ns + TOUCH_TOL >= bed.centroid_j - half_bed)
            model.Add(ns.centroid_j + half_ns <= bed.centroid_j - half_bed + TOUCH_TOL)
        else:
            model.Add(ns.centroid_j >= bed.centroid_j + half_bed - TOUCH_TOL)
            model.Add(ns.centroid_j <= bed.centroid_j + half_bed + half_ns + TOUCH_TOL)
    else:
        half_bed = bed.size_x * 50
        half_ns = ns.size_x * 50
        if side == "left":
            model.Add(ns.centroid_i + half_ns + TOUCH_TOL >= bed.centroid_i - half_bed)
            model.Add(ns.centroid_i + half_ns <= bed.centroid_i - half_bed + TOUCH_TOL)
        else:
            model.Add(ns.centroid_i >= bed.centroid_i + half_bed - TOUCH_TOL)
            model.Add(ns.centroid_i <= bed.centroid_i + half_bed + half_ns + TOUCH_TOL)


def _headboard_align(
    model: cp_model.CpModel,
    ns,
    bed,
    bed_wall: str,
) -> None:
    """Keep nightstand at the headboard end of the bed (wall side), not the foot."""
    if bed_wall == "west":
        model.Add(ns.ox <= bed.ox + HEADBOARD_CELL_TOL)
    elif bed_wall == "east":
        model.Add(ns.end_x >= bed.end_x - HEADBOARD_CELL_TOL)
    elif bed_wall == "south":
        model.Add(ns.oy <= bed.oy + HEADBOARD_CELL_TOL)
    elif bed_wall == "north":
        model.Add(ns.end_y >= bed.end_y - HEADBOARD_CELL_TOL)


def _touching_adjacent_interval(model: cp_model.CpModel, fa, fb) -> None:
    """Footprints share an edge (tighter than default adjacent)."""
    di = model.NewIntVar(0, 20000, "")
    dj = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(di, fa.centroid_i - fb.centroid_i)
    model.AddAbsEquality(dj, fa.centroid_j - fb.centroid_j)
    touch_x = fa.size_x * 50 + fb.size_x * 50
    touch_z = fa.size_y * 50 + fb.size_y * 50
    b_touch_x = model.NewBoolVar("")
    model.Add(di <= touch_x + TOUCH_TOL).OnlyEnforceIf(b_touch_x)
    model.Add(di > touch_x + TOUCH_TOL).OnlyEnforceIf(b_touch_x.Not())
    b_touch_z = model.NewBoolVar("")
    model.Add(dj <= touch_z + TOUCH_TOL).OnlyEnforceIf(b_touch_z)
    model.Add(dj > touch_z + TOUCH_TOL).OnlyEnforceIf(b_touch_z.Not())
    model.AddBoolOr([b_touch_x, b_touch_z])


def _in_front_of_interval(
    model: cp_model.CpModel,
    fa,
    fb,
    distance_m: float,
    cell_m: float,
) -> None:
    """Chair in front of desk: offset along approach axis, centered on the other."""
    dist = _offset_to_centi(distance_m, cell_m)
    model.Add(fa.centroid_i + dist <= fb.centroid_i).OnlyEnforceIf(fa.rot.Not())
    _centered_on_axis(model, fa.centroid_j, fb.centroid_j, only_if=fa.rot.Not())
    model.Add(fa.centroid_j + dist <= fb.centroid_j).OnlyEnforceIf(fa.rot)
    _centered_on_axis(model, fa.centroid_i, fb.centroid_i, only_if=fa.rot)


def _centered_on_axis(
    model: cp_model.CpModel,
    a_centroid,
    b_centroid,
    only_if=None,
) -> None:
    """Align centroids on one axis within half a grid cell."""
    diff = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(diff, a_centroid - b_centroid)
    if only_if is None:
        model.Add(diff <= CENTER_TOL)
    else:
        model.Add(diff <= CENTER_TOL).OnlyEnforceIf(only_if)


def _bed_headboard_against_wall(
    model: cp_model.CpModel,
    fv,
    wall: str,
    w_grid: int,
    l_grid: int,
) -> None:
    """Headboard edge flush to wall; bed length extends into the room."""
    if wall == "west":
        model.Add(fv.ox == 0)
        model.Add(fv.rot == 1)
    elif wall == "east":
        model.Add(fv.end_x == w_grid)
        model.Add(fv.rot == 1)
    elif wall == "south":
        model.Add(fv.oy == 0)
        model.Add(fv.rot == 0)
    elif wall == "north":
        model.Add(fv.end_y == l_grid)
        model.Add(fv.rot == 0)


def _against_wall_interval(
    model: cp_model.CpModel,
    fv,
    wall: str,
    w_grid: int,
    l_grid: int,
    soft: bool,
    category: str | None = None,
) -> None:
    if category == "bed" and wall in ("west", "east", "south", "north"):
        _bed_headboard_against_wall(model, fv, wall, w_grid, l_grid)
        return

    inset = WALL_INSET_CELLS
    if wall in WALL_BACKED_ROT and category != "bed":
        model.Add(fv.rot == WALL_BACKED_ROT[wall])
    if wall == "west":
        model.Add(fv.ox == inset)
        return
    if wall == "east":
        model.Add(fv.end_x == w_grid - inset)
        return
    if wall == "south":
        model.Add(fv.oy == inset)
        return
    if wall == "north":
        model.Add(fv.end_y == l_grid - inset)
        return

    touch_w = model.NewBoolVar("")
    touch_s = model.NewBoolVar("")
    model.Add(fv.ox == inset).OnlyEnforceIf(touch_w)
    model.Add(fv.ox != inset).OnlyEnforceIf(touch_w.Not())
    model.Add(fv.oy == inset).OnlyEnforceIf(touch_s)
    model.Add(fv.oy != inset).OnlyEnforceIf(touch_s.Not())

    touch_e = model.NewBoolVar("")
    touch_n = model.NewBoolVar("")
    model.Add(fv.end_x == w_grid - inset).OnlyEnforceIf(touch_e)
    model.Add(fv.end_x != w_grid - inset).OnlyEnforceIf(touch_e.Not())
    model.Add(fv.end_y == l_grid - inset).OnlyEnforceIf(touch_n)
    model.Add(fv.end_y != l_grid - inset).OnlyEnforceIf(touch_n.Not())

    if not soft:
        model.AddBoolOr([touch_w, touch_e, touch_s, touch_n])


def _facing_interval(model: cp_model.CpModel, fa, fb) -> None:
    """Lock fa.rot so fa faces toward fb on the dominant cardinal axis."""
    margin = FACE_TOWARD_MARGIN
    east = model.NewBoolVar("")
    west = model.NewBoolVar("")
    north = model.NewBoolVar("")
    south = model.NewBoolVar("")

    model.Add(fb.centroid_i >= fa.centroid_i + margin).OnlyEnforceIf(east)
    model.Add(fb.centroid_i <= fa.centroid_i - margin).OnlyEnforceIf(west)
    model.Add(fb.centroid_j >= fa.centroid_j + margin).OnlyEnforceIf(north)
    model.Add(fb.centroid_j <= fa.centroid_j - margin).OnlyEnforceIf(south)

    i_dom = model.NewBoolVar("")
    di = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(di, fa.centroid_i - fb.centroid_i)
    dj = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(dj, fa.centroid_j - fb.centroid_j)
    model.Add(di >= dj).OnlyEnforceIf(i_dom)
    model.Add(di < dj).OnlyEnforceIf(i_dom.Not())

    model.Add(fa.rot == 0).OnlyEnforceIf(east)
    model.Add(fa.rot == 0).OnlyEnforceIf(west)
    model.Add(fa.rot == 1).OnlyEnforceIf(north)
    model.Add(fa.rot == 1).OnlyEnforceIf(south)

    model.AddBoolOr([east, west]).OnlyEnforceIf(i_dom)
    model.AddBoolOr([north, south]).OnlyEnforceIf(i_dom.Not())


def _adjacent_chain_interval(
    model: cp_model.CpModel,
    fv_list: list,
    furniture_ids: list[str],
    wall: str,
    w_grid: int,
    l_grid: int,
) -> None:
    """Ordered pieces on one wall, pairwise edge-adjacent along the wall tangent."""
    fvs = []
    for fid in furniture_ids:
        fv = _fv_by_id(fv_list, fid)
        if fv is None:
            return
        fvs.append(fv)
    if len(fvs) < 2:
        return

    for fv in fvs:
        _against_wall_interval(
            model, fv, wall, w_grid, l_grid, soft=False, category=fv.category
        )

    tangent_axis = "j" if wall in ("north", "south") else "i"
    for a, b in zip(fvs, fvs[1:]):
        _adjacent_interval(model, a, b, hard=True)
        if tangent_axis == "j":
            model.Add(a.centroid_j <= b.centroid_j)
        else:
            model.Add(a.centroid_i <= b.centroid_i)


def _on_top_of_interval(model: cp_model.CpModel, child, parent) -> None:
    """Child shares parent grid origin (stacked decor or rug under table)."""
    model.Add(child.ox == parent.ox)
    model.Add(child.oy == parent.oy)
    model.Add(child.rot == parent.rot)


def _adjacent_interval(
    model: cp_model.CpModel, fa, fb, hard: bool = True
) -> None:
    """Pieces share an edge (touch along i or j axis)."""
    di = model.NewIntVar(0, 20000, "")
    dj = model.NewIntVar(0, 20000, "")
    model.AddAbsEquality(di, fa.centroid_i - fb.centroid_i)
    model.AddAbsEquality(dj, fa.centroid_j - fb.centroid_j)
    touch_x = model.NewIntVar(0, 20000, "")
    touch_z = model.NewIntVar(0, 20000, "")
    model.Add(touch_x == fa.size_x * 50 + fb.size_x * 50)
    model.Add(touch_z == fa.size_y * 50 + fb.size_y * 50)
    tol = 80
    b_touch_x = model.NewBoolVar("")
    model.Add(di <= touch_x + tol).OnlyEnforceIf(b_touch_x)
    model.Add(di > touch_x + tol).OnlyEnforceIf(b_touch_x.Not())
    b_touch_z = model.NewBoolVar("")
    model.Add(dj <= touch_z + tol).OnlyEnforceIf(b_touch_z)
    model.Add(dj > touch_z + tol).OnlyEnforceIf(b_touch_z.Not())
    if hard:
        model.AddBoolOr([b_touch_x, b_touch_z])


def link_footprint(*args, **kwargs) -> None:
    raise NotImplementedError("Use interval-based solver")


def add_exclusivity(*args, **kwargs) -> None:
    pass


def add_semantic_constraints(*args, **kwargs) -> None:
    add_semantic_interval(*args, **kwargs)
