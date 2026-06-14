"""Resolve role→anchor rules into FurnitureConstraint instances."""

from __future__ import annotations

from colayout.catalog.kenney_index import (
    CHAIN_ORDER,
    COUNTER_RUN_ROLES,
    placement_category,
    role_for_model,
    surface_kind_for_model,
)
from colayout.llm.anchor_structure import (
    _anchor_role_for_placement,
    _mirror_axis_for_anchor,
    _placement_matches_role,
    is_anchor_descendant,
    zone_anchor_placements,
)
from colayout.llm.room_program import default_wall_for_category
from colayout.relations.loader import (
    RoleRelationRule,
    anchor_roles_for_room,
    get_rules_for_role,
    relation_kinds,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.scene import ConstraintType, FurnitureConstraint


def _constraint_key(c: FurnitureConstraint) -> tuple:
    return (
        c.type,
        c.furniture,
        c.furniture_a,
        c.furniture_b,
        c.side,
        tuple(c.furniture_ids),
    )


def _existing_keys(constraints: list[FurnitureConstraint]) -> set[tuple]:
    return {_constraint_key(c) for c in constraints}


def _placement_role(p: FurniturePlacementDraft) -> str:
    return role_for_model(p.model_id)


def _matches_surface_kind(p: FurniturePlacementDraft, kind: str | None) -> bool:
    if not kind:
        return True
    return surface_kind_for_model(p.model_id) == kind


def _zone_anchor_ids(placements: list[FurniturePlacementDraft], room: RoomSpec) -> set[str]:
    return {a.id for a in zone_anchor_placements(placements, room)}


def _anchor_for_role(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
    anchor_role: str,
) -> FurniturePlacementDraft | None:
    for a in zone_anchor_placements(placements, room):
        if _anchor_role_for_placement(a) == anchor_role:
            return a
    for p in placements:
        if _placement_matches_role(p, anchor_role):
            return p
    return None


def _descendants_of_anchor(
    anchor_id: str,
    placements: list[FurniturePlacementDraft],
    by_id: dict[str, FurniturePlacementDraft],
) -> list[FurniturePlacementDraft]:
    return [
        p
        for p in placements
        if p.id != anchor_id and is_anchor_descendant(p, anchor_id, by_id)
    ]


def _find_by_role_in_zone(
    placements: list[FurniturePlacementDraft],
    anchor_id: str,
    by_id: dict[str, FurniturePlacementDraft],
    roles: tuple[str, ...],
    exclude_ids: set[str],
) -> FurniturePlacementDraft | None:
    for role in roles:
        for p in _descendants_of_anchor(anchor_id, placements, by_id):
            if p.id in exclude_ids:
                continue
            if _placement_role(p) == role or placement_category(p.model_id) == role:
                return p
    return None


def _resolve_target(
    child: FurniturePlacementDraft,
    rule: RoleRelationRule,
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
    by_id: dict[str, FurniturePlacementDraft],
) -> FurniturePlacementDraft | None:
    kind_spec = relation_kinds().get(rule.kind)
    if kind_spec and kind_spec.ip_type == "on_top_of" and child.on_surface_of:
        explicit = by_id.get(child.on_surface_of)
        if explicit:
            return explicit
    if kind_spec and kind_spec.ip_type == "against_wall":
        # Wall rules constrain the child itself; no pair target needed.
        return child
    for anchor_role in rule.anchor_roles:
        anchor = _anchor_for_role(placements, room, anchor_role)
        if not anchor:
            continue
        if rule.via_descendant_of:
            target = _find_by_role_in_zone(
                placements,
                anchor.id,
                by_id,
                (rule.via_descendant_of,),
                exclude_ids={child.id},
            )
            if target:
                return target
        if rule.target_child_roles:
            target = _find_by_role_in_zone(
                placements,
                anchor.id,
                by_id,
                rule.target_child_roles,
                exclude_ids={child.id},
            )
            if target:
                return target
        if child.id != anchor.id:
            return anchor
        if anchor_role == _anchor_role_for_placement(child):
            if rule.target_child_roles:
                return _find_by_role_in_zone(
                    placements,
                    anchor.id,
                    by_id,
                    rule.target_child_roles,
                    exclude_ids={child.id},
                )
    return None


def _has_draft_link(
    child: FurniturePlacementDraft,
    target_id: str,
    ip_type: str,
) -> bool:
    if ip_type == "on_top_of" and child.on_surface_of == target_id:
        return True
    if ip_type in ("under", "centered_under") and child.on_surface_of == target_id:
        return True
    if ip_type == "relative_position" and child.relative_to == target_id:
        return True
    return False


def _flank_side_for_child(
    child: FurniturePlacementDraft,
    anchor: FurniturePlacementDraft,
    default: str,
) -> str:
    if child.id.endswith("_r") or child.id.endswith("_right"):
        return "right"
    if child.id.endswith("_l") or child.id.endswith("_left"):
        return "left"
    if child.center_z_m < anchor.center_z_m - 0.05:
        return "left"
    if child.center_z_m > anchor.center_z_m + 0.05:
        return "right"
    if child.center_x_m < anchor.center_x_m:
        return "left"
    return default or "right"


def _rule_key(child_role: str, room_type: str, rule: RoleRelationRule) -> str:
    return f"{room_type}.{child_role}.{rule.kind}.{rule.priority}"


def _emit_constraint(
    rule: RoleRelationRule,
    child: FurniturePlacementDraft,
    target: FurniturePlacementDraft,
    room: RoomSpec,
    *,
    child_role: str,
) -> FurnitureConstraint | None:
    kind_spec = relation_kinds().get(rule.kind)
    if not kind_spec:
        return None
    ip_type = kind_spec.ip_type
    weight = rule.weight if rule.weight is not None else kind_spec.default_weight

    if ip_type == "against_wall":
        wall = rule.wall or default_wall_for_category(
            placement_category(child.model_id), room.type
        )
        if not wall:
            return None
        return FurnitureConstraint(
            type=ConstraintType.AGAINST_WALL,
            furniture=child.id,
            wall=wall,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "flank":
        flank_side = rule.side or _flank_side_for_child(
            child, target, kind_spec.side or "left"
        )
        return FurnitureConstraint(
            type=ConstraintType.FLANK,
            furniture_a=child.id,
            furniture_b=target.id,
            side=flank_side,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "facing":
        return FurnitureConstraint(
            type=ConstraintType.FACING,
            furniture_a=child.id,
            furniture_b=target.id,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "in_front_of":
        return FurnitureConstraint(
            type=ConstraintType.IN_FRONT_OF,
            furniture_a=child.id,
            furniture_b=target.id,
            distance_m=rule.distance_m,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "adjacent":
        return FurnitureConstraint(
            type=ConstraintType.ADJACENT,
            furniture_a=child.id,
            furniture_b=target.id,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "on_top_of":
        return FurnitureConstraint(
            type=ConstraintType.ON_TOP_OF,
            furniture_a=child.id,
            furniture_b=target.id,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "under":
        return FurnitureConstraint(
            type=ConstraintType.UNDER,
            furniture_a=child.id,
            furniture_b=target.id,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "centered_under":
        return FurnitureConstraint(
            type=ConstraintType.CENTERED_UNDER,
            furniture_a=child.id,
            furniture_b=target.id,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "relative_position":
        return FurnitureConstraint(
            type=ConstraintType.RELATIVE_POSITION,
            furniture_a=target.id,
            furniture_b=child.id,
            offset_i=rule.offset_i,
            offset_j=rule.offset_j,
            hard=rule.hard,
            weight=weight,
        )
    if ip_type == "seats_around":
        return FurnitureConstraint(
            type=ConstraintType.SEATS_AROUND,
            furniture=target.id,
            min_seats=2,
            hard=rule.hard,
            weight=weight,
        )
    return None


def _counter_chain_constraint(
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
    keys: set[tuple],
) -> FurnitureConstraint | None:
    """Single ADJACENT_CHAIN over all counter-run pieces, ordered by role."""
    run = [p for p in placements if _placement_role(p) in COUNTER_RUN_ROLES]
    if len(run) < 2:
        return None
    run.sort(key=lambda p: (CHAIN_ORDER.get(_placement_role(p), 99), p.id))
    wall = default_wall_for_category("counter", room.type) or "north"
    c = FurnitureConstraint(
        type=ConstraintType.ADJACENT_CHAIN,
        furniture_ids=[p.id for p in run],
        wall=wall,
        hard=False,
        weight=16.0,
    )
    if _constraint_key(c) in keys:
        return None
    return c


def _symmetric_pair_constraints(
    rule: RoleRelationRule,
    role: str,
    placements: list[FurniturePlacementDraft],
    room: RoomSpec,
    by_id: dict[str, FurniturePlacementDraft],
    keys: set[tuple],
) -> list[FurnitureConstraint]:
    """Mirror same-role pairs about their zone anchor centroid."""
    out: list[FurnitureConstraint] = []
    for anchor_role in rule.anchor_roles:
        anchor = _anchor_for_role(placements, room, anchor_role)
        if not anchor:
            continue
        group = [
            p
            for p in placements
            if p.id != anchor.id
            and _placement_role(p) == role
            and not p.on_surface_of
        ]
        group.sort(key=lambda p: p.id)
        axis = _mirror_axis_for_anchor(anchor, room.type)
        for a, b in zip(group[0::2], group[1::2]):
            c = FurnitureConstraint(
                type=ConstraintType.SYMMETRIC_PAIR,
                furniture=anchor.id,
                furniture_a=a.id,
                furniture_b=b.id,
                axis=axis,
                hard=rule.hard,
                weight=rule.weight or 12.0,
            )
            key = _constraint_key(c)
            if key in keys:
                continue
            keys.add(key)
            out.append(c)
    return out


def resolve_role_constraints(
    draft: RoomLayoutDraft,
    room: RoomSpec,
    existing: list[FurnitureConstraint],
) -> list[FurnitureConstraint]:
    """Emit config-driven constraints for placements not already covered."""
    placements = draft.placements
    by_id = {p.id: p for p in placements}
    zone_ids = _zone_anchor_ids(placements, room)
    keys = _existing_keys(existing)
    out: list[FurnitureConstraint] = []
    seats_around_targets: set[str] = {
        c.furniture
        for c in existing
        if c.type == ConstraintType.SEATS_AROUND and c.furniture
    }
    constrained_children: set[str] = {
        c.furniture_a for c in existing if c.furniture_a
    } | {c.furniture for c in existing if c.furniture}
    chain_requested = False

    # Pieces serving as the pedestal of a zone anchor (e.g. the console under
    # the TV): their position is governed by the anchor's own rules plus the
    # stacking lock, so sibling pairwise rules must not tug them elsewhere.
    room_anchor_roles = anchor_roles_for_room(room.type)
    anchor_pedestal_ids: set[str] = {
        p.on_surface_of
        for p in placements
        if p.on_surface_of and _placement_role(p) in room_anchor_roles
    }

    # Group rules (symmetric pairs) run per-role up front so a non-additive
    # pairwise rule on the same role cannot shadow them.
    sym_roles_done: set[str] = set()
    for p in placements:
        role = _placement_role(p)
        if role in sym_roles_done:
            continue
        sym_roles_done.add(role)
        for rule in get_rules_for_role(role, room.type):
            kind_spec = relation_kinds().get(rule.kind)
            if kind_spec and kind_spec.ip_type == "symmetric_pair":
                out.extend(
                    _symmetric_pair_constraints(
                        rule, role, placements, room, by_id, keys
                    )
                )

    for p in placements:
        if p.id in anchor_pedestal_ids:
            continue
        role = _placement_role(p)
        rules = get_rules_for_role(role, room.type)
        if not rules:
            continue

        for rule in rules:
            if rule.surface_kind and not _matches_surface_kind(p, rule.surface_kind):
                continue

            kind_spec = relation_kinds().get(rule.kind)
            if not kind_spec:
                continue
            if kind_spec.ip_type == "adjacent_chain":
                chain_requested = True
                continue
            if kind_spec.ip_type == "symmetric_pair":
                continue
            if (
                kind_spec.ip_type == "seats_around"
                and _placement_role(p) == "chair"
            ):
                anchor = _anchor_for_role(placements, room, rule.anchor_roles[0])
                if anchor and anchor.id in seats_around_targets:
                    continue

            if p.id in zone_ids and not role_specs_is_anchor(role):
                target = _resolve_target(p, rule, placements, room, by_id)
            elif p.id in zone_ids:
                target = _resolve_target(p, rule, placements, room, by_id)
            else:
                if p.id in constrained_children and rule.kind not in (
                    "flank_left",
                    "flank_right",
                ):
                    continue
                target = _resolve_target(p, rule, placements, room, by_id)

            if not target:
                continue
            if _has_draft_link(p, target.id, kind_spec.ip_type):
                break

            c = _emit_constraint(rule, p, target, room, child_role=role)
            if not c:
                continue
            c = c.model_copy(update={"rule_key": _rule_key(role, room.type, rule)})
            key = _constraint_key(c)
            if key in keys:
                if not rule.additive:
                    break
                continue
            keys.add(key)
            out.append(c)
            if c.type == ConstraintType.SEATS_AROUND and c.furniture:
                seats_around_targets.add(c.furniture)
            constrained_children.add(p.id)
            if not rule.additive:
                break

    if chain_requested:
        chain = _counter_chain_constraint(placements, room, keys)
        if chain:
            keys.add(_constraint_key(chain))
            out.append(chain)

    return out


def role_specs_is_anchor(role: str) -> bool:
    from colayout.relations.loader import role_specs

    spec = role_specs().get(role)
    return bool(spec and spec.is_anchor)
