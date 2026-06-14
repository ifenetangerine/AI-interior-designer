"""Anchor zones: count scales with room size; each anchor needs min children."""

from __future__ import annotations

from typing import Literal

from colayout.catalog.kenney_index import (
    catalog_for_room,
    is_allowed_in_room,
    load_catalog,
    placement_category,
    role_for_model,
)
from colayout.llm.mock_layouts import load_mock_layout
from colayout.llm.room_program import default_wall_for_category, density_tier, room_area_m2
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.scene import ConstraintType, FurnitureConstraint

MIN_CHILDREN_PER_ANCHOR: dict[str, dict[str, int]] = {
    "bedroom": {"bed": 4, "desk": 1, "dresser": 1},
    "living_room": {"tv": 4, "bookshelf": 2, "storage_cabinet": 2},
    "kitchen": {"dining_table": 4, "sink": 2, "counter_bar": 2},
}

_DEFAULT_MIN_CHILDREN = 4


def min_children_for_anchor(room_type: str, anchor_role: str) -> int:
    """Minimum relative_to descendants required for one anchor role in a room type."""
    return MIN_CHILDREN_PER_ANCHOR.get(room_type, {}).get(
        anchor_role, _DEFAULT_MIN_CHILDREN
    )

ANCHOR_COUNT_BY_TIER: dict[str, dict[str, int]] = {
    "bedroom": {"compact": 1, "standard": 2, "spacious": 3},
    "living_room": {"compact": 2, "standard": 2, "spacious": 3},
    "kitchen": {"compact": 2, "standard": 2, "spacious": 3},
}

# (role, zone) in placement_order priority; first N roles used per tier anchor count.
ROOM_ANCHOR_SPECS: dict[str, list[tuple[str, str]]] = {
    "bedroom": [("bed", "sleep"), ("desk", "work"), ("dresser", "storage")],
    "living_room": [
        ("tv", "viewing"),
        ("bookshelf", "reading"),
        ("storage_cabinet", "storage"),
    ],
    "kitchen": [
        ("dining_table", "dining"),
        ("sink", "kitchen"),
        ("counter_bar", "kitchen"),
    ],
}

# Soft LLM hints only — never used to auto-place furniture.
ANCHOR_CHILD_HINTS: dict[str, str] = {
    "bed": "nightstands, wardrobe, lamps, rug, or other sleep-zone pieces that fit the room",
    "desk": "chair, task lamp, plant, or side table suited to a work corner",
    "dresser": "mirror, table lamp, plant, or accent decor for the storage zone",
    "tv": (
        "TV screen on a console/side table (on_surface_of tv_console); "
        "sofa facing the screen, coffee table, side tables, accent seating, or rug"
    ),
    "bookshelf": "plant, lamp, reading chair, or side table for a reading nook",
    "storage_cabinet": (
        "drawer table, cabinet, or bookcase segment; "
        "link lamps, plants, or accent decor relative_to this anchor"
    ),
    "dining_table": "dining chairs and any dining-zone decor that fits",
    "sink": (
        "counter run, stove, fridge, and other kitchen pieces chained from the sink; "
        "small decor/plants may use on_surface_of on counter_base segments"
    ),
    "counter_bar": "bar stools, chairs, plants, or lamps near the bar",
}

_DEFAULT_CHILD_HINT = "support/accent pieces that belong in this zone"


def anchor_count_for_room(room: RoomSpec) -> int:
    tier = density_tier(room_area_m2(room))
    by_tier = ANCHOR_COUNT_BY_TIER.get(room.type, {"standard": 1})
    return by_tier.get(tier, 1)


def anchor_specs_for_room(room: RoomSpec) -> list[tuple[str, str]]:
    specs = ROOM_ANCHOR_SPECS.get(room.type, [("tv", "viewing")])
    return specs[: anchor_count_for_room(room)]


_TV_LEGACY_ROLES = frozenset({"tv", "tv_stand"})


def _placement_matches_role(p: FurniturePlacementDraft, role: str) -> bool:
    model_role = role_for_model(p.model_id)
    cat = placement_category(p.model_id)
    if role == "tv":
        return model_role in _TV_LEGACY_ROLES or cat in _TV_LEGACY_ROLES
    return model_role == role or cat == role


def resolve_anchor_placements(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> list[FurniturePlacementDraft]:
    """Identify anchor pieces for this room tier (expected roles, then composition_role)."""
    need = anchor_count_for_room(room)
    expected = anchor_specs_for_room(room)
    anchors: list[FurniturePlacementDraft] = []
    used_ids: set[str] = set()

    tagged = sorted(
        [p for p in placements if p.composition_role == "anchor"],
        key=lambda p: p.placement_order,
    )
    for p in tagged:
        if p.id not in used_ids:
            anchors.append(p)
            used_ids.add(p.id)
        if len(anchors) >= need:
            return anchors[:need]

    for role, _zone in expected:
        candidates = sorted(
            [
                p
                for p in placements
                if p.id not in used_ids and _placement_matches_role(p, role)
            ],
            key=lambda p: p.placement_order,
        )
        if candidates:
            anchors.append(candidates[0])
            used_ids.add(candidates[0].id)
        if len(anchors) >= need:
            return anchors[:need]

    for p in sorted(placements, key=lambda x: x.placement_order):
        if p.id in used_ids:
            continue
        anchors.append(p)
        used_ids.add(p.id)
        if len(anchors) >= need:
            break
    return anchors[:need]


def is_anchor_descendant(
    placement: FurniturePlacementDraft,
    anchor_id: str,
    by_id: dict[str, FurniturePlacementDraft],
) -> bool:
    cur_id = placement.relative_to
    visited: set[str] = set()
    while cur_id and cur_id not in visited:
        if cur_id == anchor_id:
            return True
        visited.add(cur_id)
        parent = by_id.get(cur_id)
        cur_id = parent.relative_to if parent else None
    return False


def _anchor_id_set(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> set[str]:
    return {a.id for a in resolve_anchor_placements(placements, room)}


def count_anchor_children(
    anchor_id: str,
    placements: list[FurniturePlacementDraft],
    *,
    room: RoomSpec | None = None,
    other_anchor_ids: set[str] | None = None,
) -> int:
    by_id = {p.id: p for p in placements}
    skip = other_anchor_ids
    if skip is None and room is not None:
        skip = _anchor_id_set(placements, room)
    skip = skip or set()
    return sum(
        1
        for p in placements
        if p.id != anchor_id
        and p.id not in skip
        and is_anchor_descendant(p, anchor_id, by_id)
    )


MAX_CHILD_DISTANCE_M = 2.5

# Wall-hug pieces use against_wall; skip anchor relative_position for them.
SKIP_ANCHOR_RELATIVE_ROLES = frozenset(
    {
        "desk",
        "wardrobe",
        "dresser",
        "fridge",
        "sink",
        "stove",
        "tv_stand",
        "tv_console",
        "storage_cabinet",
        "counter_end",
        "counter_bar",
        "counter_base",
    }
)


def anchor_relative_constraints(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> list[FurnitureConstraint]:
    """Soft IP anchors: keep children near their zone anchor at LLM offsets."""
    anchors = resolve_anchor_placements(placements, room)
    by_id = {p.id: p for p in placements}
    out: list[FurnitureConstraint] = []
    seen: set[tuple[str, str]] = set()
    for anchor in anchors:
        ax, az = anchor.center_x_m, anchor.center_z_m
        for p in placements:
            if p.id == anchor.id:
                continue
            if p.relative_to != anchor.id:
                continue
            if role_for_model(p.model_id) in SKIP_ANCHOR_RELATIVE_ROLES:
                continue
            if p.on_surface_of:
                continue
            key = (anchor.id, p.id)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                FurnitureConstraint(
                    type=ConstraintType.RELATIVE_POSITION,
                    furniture_a=anchor.id,
                    furniture_b=p.id,
                    offset_i=p.center_x_m - ax,
                    offset_j=p.center_z_m - az,
                )
            )
    return out


def _mirror_axis_for_anchor(
    anchor: FurniturePlacementDraft,
    room_type: str,
) -> Literal["i", "j"]:
    """Reflection axis through anchor centroid (i=left/right, j=north/south)."""
    cat = placement_category(anchor.model_id)
    role = role_for_model(anchor.model_id)
    wall = default_wall_for_category(cat or role, room_type)
    if wall in ("west", "east"):
        return "j"
    return "i"


_DINING_CHAIR_ROLES = frozenset({"chair"})


def _is_dining_chair_child(p: FurniturePlacementDraft) -> bool:
    role = role_for_model(p.model_id)
    cat = placement_category(p.model_id)
    return role in _DINING_CHAIR_ROLES or cat in _DINING_CHAIR_ROLES


def _classify_side_of_anchor(
    child: FurniturePlacementDraft,
    anchor: FurniturePlacementDraft,
) -> Literal["north", "south", "east", "west"]:
    di = child.center_x_m - anchor.center_x_m
    dj = child.center_z_m - anchor.center_z_m
    if abs(dj) >= abs(di):
        return "north" if dj > 0 else "south"
    return "east" if di > 0 else "west"


def _pair_opposite_side_chairs(
    anchor: FurniturePlacementDraft,
    side_a: list[FurniturePlacementDraft],
    side_b: list[FurniturePlacementDraft],
    axis: Literal["i", "j"],
    seen: set[tuple[str, str, str]],
) -> list[FurnitureConstraint]:
    """Pair chairs on opposite sides of a dining table, sorted along the parallel axis."""
    parallel = (
        (lambda p: p.center_x_m) if axis == "j" else (lambda p: p.center_z_m)
    )
    a_sorted = sorted(side_a, key=parallel)
    b_sorted = sorted(side_b, key=parallel)
    out: list[FurnitureConstraint] = []
    for a, b in zip(a_sorted, b_sorted):
        key = (anchor.id, min(a.id, b.id), max(a.id, b.id))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            FurnitureConstraint(
                type=ConstraintType.SYMMETRIC_PAIR,
                furniture=anchor.id,
                furniture_a=a.id,
                furniture_b=b.id,
                axis=axis,
                hard=False,
            )
        )
    return out


def _dining_table_chair_symmetric_pairs(
    anchor: FurniturePlacementDraft,
    placements: list[FurniturePlacementDraft],
    by_id: dict[str, FurniturePlacementDraft],
    anchor_ids: set[str],
    seen: set[tuple[str, str, str]],
) -> list[FurnitureConstraint]:
    """Pair dining chairs on opposite sides of the table (N↔S on j, E↔W on i)."""
    by_side: dict[str, list[FurniturePlacementDraft]] = {
        "north": [],
        "south": [],
        "east": [],
        "west": [],
    }
    for p in placements:
        if p.id in anchor_ids:
            continue
        if not is_anchor_descendant(p, anchor.id, by_id):
            continue
        if p.on_surface_of or not _is_dining_chair_child(p):
            continue
        by_side[_classify_side_of_anchor(p, anchor)].append(p)

    out: list[FurnitureConstraint] = []
    out.extend(
        _pair_opposite_side_chairs(
            anchor, by_side["north"], by_side["south"], "j", seen
        )
    )
    out.extend(
        _pair_opposite_side_chairs(
            anchor, by_side["east"], by_side["west"], "i", seen
        )
    )
    return out


def anchor_symmetric_pair_constraints(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> list[FurnitureConstraint]:
    """Soft IP: paired same-role children mirror about the anchor centroid."""
    zone_anchors = zone_anchor_placements(placements, room)
    by_id = {p.id: p for p in placements}
    anchor_ids = {a.id for a in zone_anchors}
    out: list[FurnitureConstraint] = []
    seen: set[tuple[str, str, str]] = set()

    for anchor in zone_anchors:
        anchor_role = role_for_model(anchor.model_id)
        anchor_cat = placement_category(anchor.model_id)
        if anchor_role == "dining_table" or anchor_cat == "dining_table":
            out.extend(
                _dining_table_chair_symmetric_pairs(
                    anchor, placements, by_id, anchor_ids, seen
                )
            )

        axis = _mirror_axis_for_anchor(anchor, room.type)
        by_role: dict[str, list[FurniturePlacementDraft]] = {}
        for p in placements:
            if p.id in anchor_ids:
                continue
            if not is_anchor_descendant(p, anchor.id, by_id):
                continue
            if p.on_surface_of:
                continue
            child_role = role_for_model(p.model_id)
            if anchor_role == "bed" and child_role == "nightstand":
                continue
            if (
                anchor_role == "dining_table" or anchor_cat == "dining_table"
            ) and child_role in _DINING_CHAIR_ROLES:
                continue
            by_role.setdefault(child_role, []).append(p)

        for _role, group in by_role.items():
            if len(group) < 2 or len(group) % 2 != 0:
                continue
            # Mirror outermost with outermost, inner with inner, along the
            # mirrored coordinate (groups of 4 become two nested pairs).
            coord = (
                (lambda p: p.center_x_m)
                if axis == "i"
                else (lambda p: p.center_z_m)
            )
            ordered = sorted(group, key=coord)
            n = len(ordered)
            for k in range(n // 2):
                a, b = ordered[k], ordered[n - 1 - k]
                key = (anchor.id, min(a.id, b.id), max(a.id, b.id))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    FurnitureConstraint(
                        type=ConstraintType.SYMMETRIC_PAIR,
                        furniture=anchor.id,
                        furniture_a=a.id,
                        furniture_b=b.id,
                        axis=axis,
                        hard=False,
                    )
                )
    return out


def check_relative_position_sanity(
    placements: list[FurniturePlacementDraft],
) -> str | None:
    """Warn when a relative_to child is implausibly far from its parent."""
    by_id = {p.id: p for p in placements}
    drifted: list[str] = []
    for p in placements:
        if not p.relative_to or p.relative_to not in by_id:
            continue
        parent = by_id[p.relative_to]
        dist = (
            (p.center_x_m - parent.center_x_m) ** 2
            + (p.center_z_m - parent.center_z_m) ** 2
        ) ** 0.5
        if dist > MAX_CHILD_DISTANCE_M:
            drifted.append(f"{p.id}→{p.relative_to} ({dist:.1f} m)")
    if drifted:
        return (
            f"(warning) relative_to drift: children far from parent — "
            f"{', '.join(drifted[:4])}"
        )
    return None


def build_anchor_debug(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> dict:
    """Serializable anchor → children tree for the 3D viewer debug overlay."""
    anchors = resolve_anchor_placements(placements, room)
    by_id = {p.id: p for p in placements}
    anchor_ids = {a.id for a in anchors}
    anchor_rows: list[dict] = []
    for anchor in anchors:
        role = role_for_model(anchor.model_id)
        children: list[dict] = []
        for p in placements:
            if p.id == anchor.id or p.id in anchor_ids:
                continue
            if not is_anchor_descendant(p, anchor.id, by_id):
                continue
            children.append(
                {
                    "id": p.id,
                    "model_id": p.model_id,
                    "role": role_for_model(p.model_id),
                    "center_x_m": p.center_x_m,
                    "center_z_m": p.center_z_m,
                    "relative_to": p.relative_to,
                    "composition_role": p.composition_role,
                    "note": p.note,
                }
            )
        anchor_rows.append(
            {
                "id": anchor.id,
                "model_id": anchor.model_id,
                "role": role,
                "zone": anchor.zone,
                "composition_role": anchor.composition_role,
                "center_x_m": anchor.center_x_m,
                "center_z_m": anchor.center_z_m,
                "min_children": min_children_for_anchor(room.type, role),
                "child_count": len(children),
                "children": children,
            }
        )
    return {
        "room_type": room.type,
        "tier": density_tier(room_area_m2(room)),
        "anchor_count": anchor_count_for_room(room),
        "anchors": anchor_rows,
    }


def zone_anchor_placements(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> list[FurniturePlacementDraft]:
    """Zone roots: prefer explicit composition_role=anchor, else role-matched anchors."""
    tagged = sorted(
        [p for p in placements if p.composition_role == "anchor"],
        key=lambda p: p.placement_order,
    )
    if tagged:
        need = anchor_count_for_room(room)
        return tagged[:need]

    expected_roles = {role for role, _ in anchor_specs_for_room(room)}
    anchors = resolve_anchor_placements(placements, room)
    zone: list[FurniturePlacementDraft] = []
    for anchor in anchors:
        role = role_for_model(anchor.model_id)
        if role in expected_roles or placement_category(anchor.model_id) in expected_roles:
            zone.append(anchor)
    return zone


def is_in_anchor_group(
    placement: FurniturePlacementDraft,
    zone_anchors: list[FurniturePlacementDraft],
    by_id: dict[str, FurniturePlacementDraft],
) -> bool:
    """True if placement is a zone anchor or chains to one via relative_to."""
    zone_ids = {a.id for a in zone_anchors}
    if placement.id in zone_ids:
        return True
    return any(
        is_anchor_descendant(placement, anchor.id, by_id)
        for anchor in zone_anchors
    )


def check_orphan_placements(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> str | None:
    """Warn when furniture is not linked into any anchor zone."""
    zone_anchors = zone_anchor_placements(placements, room)
    if not zone_anchors:
        return None
    by_id = {p.id: p for p in placements}
    orphans = [
        p.id
        for p in placements
        if not is_in_anchor_group(p, zone_anchors, by_id)
    ]
    if orphans:
        return (
            "(warning) orphan placements: every piece must belong to an anchor group "
            f"(relative_to an anchor or a chained child) — remove or link: "
            f"{', '.join(orphans[:6])}"
        )
    return None


def check_anchor_structure(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> str | None:
    need_anchors = anchor_count_for_room(room)
    anchors = resolve_anchor_placements(placements, room)
    if len(anchors) < need_anchors:
        return (
            f"(warning) structure: expected {need_anchors} anchor(s) for "
            f"{density_tier(room_area_m2(room))} {room.type}, "
            f"found {len(anchors)} — tag more pieces with composition_role anchor"
        )
    short: list[str] = []
    anchor_ids = {a.id for a in anchors}
    for anchor in anchors:
        role = _anchor_role_for_placement(anchor)
        required = min_children_for_anchor(room.type, role)
        n = count_anchor_children(
            anchor.id, placements, other_anchor_ids=anchor_ids
        )
        if n < required:
            short.append(f"{anchor.id} ({role}: {n}/{required})")
    if short:
        return (
            "(warning) structure: anchor(s) need more children via relative_to "
            f"(direct or chained): {', '.join(short)}"
        )
    return None


def anchor_structure_guidance(room: RoomSpec) -> str:
    tier = density_tier(room_area_m2(room))
    n = anchor_count_for_room(room)
    specs = anchor_specs_for_room(room)
    lines = [
        f"Suggested anchor zones ({tier} tier, place ~{n} anchor(s), "
        "min children per anchor via relative_to):",
    ]
    for i, (role, zone) in enumerate(specs, start=1):
        required = min_children_for_anchor(room.type, role)
        child_hint = ANCHOR_CHILD_HINTS.get(role, _DEFAULT_CHILD_HINT)
        lines.append(
            f"  Suggestion {i}: consider a {role.replace('_', ' ')} anchor "
            f"(composition_role anchor, zone {zone}, ≥{required} linked pieces). "
            f"Choose catalog model_ids you prefer; children: {child_hint}."
        )
    lines.append(
        "Anchors are zone roots: set relative_to null on every composition_role anchor."
    )
    lines.append(
        "Do not add furniture that is not part of an anchor group. Every non-anchor piece "
        "must set relative_to its zone anchor or another piece already in that zone's chain."
    )
    lines.append(
        "Build each zone symmetrically around its anchor: the anchor is the focal axis; "
        "place paired children (two nightstands, two side tables, two chairs, etc.) as "
        "mirrored reflections on opposite sides when possible."
    )
    lines.append(
        "Pick child roles from the catalog that fit the room — no fixed shopping list. "
        "If a piece cannot be linked to an anchor, omit it."
    )
    return "\n".join(lines)


def _model_for_role(role: str, room_type: str) -> str | None:
    catalog = load_catalog()
    default = catalog.get("category_defaults", {}).get(role)
    if default and is_allowed_in_room(default, room_type):
        return default
    for row in catalog_for_room(room_type):
        if row["role"] == role:
            return row["id"]
    return None


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def _template_by_role(room: RoomSpec) -> dict[str, dict]:
    try:
        template = load_mock_layout(room)
    except ValueError:
        return {}
    by_role: dict[str, dict] = {}
    for raw in template.get("placements", []):
        role = role_for_model(raw["model_id"])
        if role not in by_role:
            by_role[role] = raw
    return by_role


def _anchor_role_for_placement(p: FurniturePlacementDraft) -> str:
    role = role_for_model(p.model_id)
    if role in _TV_LEGACY_ROLES or placement_category(p.model_id) in _TV_LEGACY_ROLES:
        return "tv"
    return role


def _dist_to_anchor(
    p: FurniturePlacementDraft, anchor: FurniturePlacementDraft
) -> float:
    return (
        (p.center_x_m - anchor.center_x_m) ** 2
        + (p.center_z_m - anchor.center_z_m) ** 2
    ) ** 0.5


def link_orphan_placements(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
) -> tuple[list[FurniturePlacementDraft], list[str]]:
    """Attach ungrouped pieces to the nearest zone anchor via relative_to."""
    zone_anchors = zone_anchor_placements(placements, room)
    if not zone_anchors:
        return placements, []
    by_id = {p.id: p for p in placements}
    messages: list[str] = []
    updated: list[FurniturePlacementDraft] = []
    for p in placements:
        if p.composition_role == "anchor":
            updated.append(p)
            continue
        if is_in_anchor_group(p, zone_anchors, by_id):
            updated.append(p)
            continue
        nearest = min(zone_anchors, key=lambda a: _dist_to_anchor(p, a))
        updated.append(p.model_copy(update={"relative_to": nearest.id}))
        messages.append(
            f"(info) linked orphan '{p.id}' to anchor '{nearest.id}'"
        )
    return updated, messages


def _ensure_tv_viewing_stack(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
    used_ids: set[str],
    template: dict[str, dict],
    messages: list[str],
) -> list[FurniturePlacementDraft]:
    """Viewing anchor is a TV screen stacked on a console table."""
    anchors = resolve_anchor_placements(placements, room)
    tv_anchor = next(
        (a for a in anchors if _anchor_role_for_placement(a) == "tv"), None
    )
    if not tv_anchor:
        return placements

    updated = list(placements)
    by_id = {p.id: p for p in updated}
    tv_idx = next(i for i, p in enumerate(updated) if p.id == tv_anchor.id)
    tv = updated[tv_idx]

    if role_for_model(tv.model_id) == "tv_stand":
        replacement = _model_for_role("tv", room.type) or "televisionModern"
        updated[tv_idx] = tv.model_copy(update={"model_id": replacement})
        tv = updated[tv_idx]
        messages.append(
            f"(info) replaced legacy tv_stand model on '{tv.id}' with '{replacement}'"
        )

    console_id = tv.on_surface_of
    console = by_id.get(console_id) if console_id else None
    if console is None:
        for p in updated:
            if p.relative_to != tv.id:
                continue
            parent_role = role_for_model(p.model_id)
            parent_cat = placement_category(p.model_id)
            if parent_role in ("nightstand", "tv_console") or parent_cat in (
                "side_table",
                "nightstand",
            ):
                console = p
                console_id = p.id
                break
    if console is None:
        console_id = _unique_id("tv_console", used_ids)
        tpl = template.get("tv_console") or template.get("side_table")
        if tpl:
            cx, cz = float(tpl["center_x_m"]), float(tpl["center_z_m"])
            orient = int(tpl.get("orientation", 0))
            mid = tpl["model_id"]
            model_id = mid if is_allowed_in_room(mid, room.type) else "sideTable"
        else:
            cx, cz = tv.center_x_m, tv.center_z_m - 0.05
            orient = tv.orientation
            model_id = _model_for_role("tv_console", room.type) or "sideTable"
        console = FurniturePlacementDraft(
            id=console_id,
            model_id=model_id,
            placement_order=tv.placement_order + 1,
            center_x_m=cx,
            center_z_m=cz,
            orientation=orient,
            relative_to=tv.id,
            note="console under TV anchor",
        )
        updated.append(console)
        used_ids.add(console_id)
        messages.append(f"(info) added TV console '{console_id}' under anchor '{tv.id}'")

    if tv.on_surface_of != console.id:
        updated[tv_idx] = tv.model_copy(update={"on_surface_of": console.id})
    if console.relative_to != tv.id:
        for i, p in enumerate(updated):
            if p.id == console.id:
                updated[i] = p.model_copy(update={"relative_to": tv.id})
                break

    return updated


def ensure_anchor_children(
    draft: RoomLayoutDraft,
    room: RoomSpec,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Ensure expected anchor zones exist and are tagged; never auto-adds child furniture."""
    messages: list[str] = []
    placements = list(draft.placements)
    used_ids = {p.id for p in placements}
    template = _template_by_role(room)
    specs = anchor_specs_for_room(room)

    # Ensure expected anchor roles exist.
    for i, (role, zone) in enumerate(specs):
        if any(_placement_matches_role(p, role) for p in placements):
            continue
        model_id = _model_for_role(role, room.type)
        if not model_id:
            continue
        tpl = template.get(role)
        fid = _unique_id(role.replace("_", ""), used_ids)
        if tpl:
            cx, cz = float(tpl["center_x_m"]), float(tpl["center_z_m"])
            orient = int(tpl.get("orientation", 0))
            mid = tpl["model_id"]
            if is_allowed_in_room(mid, room.type):
                model_id = mid
        else:
            cx, cz = room.width_m * (0.35 + 0.15 * i), room.length_m * 0.5
            orient = 0
        placements.append(
            FurniturePlacementDraft(
                id=fid,
                model_id=model_id,
                placement_order=i + 1,
                center_x_m=cx,
                center_z_m=cz,
                orientation=orient,
                composition_role="anchor",
                zone=zone,
                note=f"auto-added {role} anchor for {density_tier(room_area_m2(room))} tier",
            )
        )
        used_ids.add(fid)
        messages.append(f"(info) auto-added anchor {role} as '{fid}'")

    # Tag anchors and strip relative_to — anchors are zone roots, not children.
    anchors = resolve_anchor_placements(placements, room)
    spec_zones = {role: zone for role, zone in specs}
    updated: list[FurniturePlacementDraft] = []
    anchor_ids = {a.id for a in anchors}
    for p in placements:
        if p.id not in anchor_ids:
            updated.append(p)
            continue
        role = role_for_model(p.model_id)
        patch: dict = {
            "composition_role": "anchor",
            "zone": p.zone or spec_zones.get(role),
        }
        if p.relative_to is not None:
            patch["relative_to"] = None
        updated.append(p.model_copy(update=patch))
    placements = updated

    placements = _ensure_tv_viewing_stack(
        placements, room, used_ids, template, messages
    )
    placements, orphan_msgs = link_orphan_placements(placements, room)
    messages.extend(orphan_msgs)

    return draft.model_copy(update={"placements": placements}), messages
