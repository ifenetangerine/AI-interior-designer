"""Load furniture_anchor_relations.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from colayout.catalog.kenney_index import load_catalog
from colayout.llm.anchor_structure import ROOM_ANCHOR_SPECS

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config" / "furniture_anchor_relations.yaml"


@dataclass(frozen=True)
class RelationKindSpec:
    ip_type: str
    side: str | None = None
    default_weight: float = 8.0


@dataclass(frozen=True)
class RoleRelationRule:
    kind: str
    room_types: tuple[str, ...]
    anchor_roles: tuple[str, ...]
    hard: bool = False
    weight: float | None = None
    priority: int = 10
    via_descendant_of: str | None = None
    target_child_roles: tuple[str, ...] = ()
    offset_i: float = 0.0
    offset_j: float = 0.0
    distance_m: float = 0.7
    side: str | None = None
    surface_kind: str | None = None
    wall: str | None = None
    additive: bool = False  # emit and keep trying later rules for this piece


@dataclass
class RoleRelationSpec:
    is_anchor: bool = False
    relations: list[RoleRelationRule] = field(default_factory=list)


def _parse_rule(raw: dict[str, Any]) -> RoleRelationRule:
    room_types = tuple(raw.get("room_types") or ["*"])
    anchor_roles = tuple(raw.get("anchor_roles") or [])
    target = raw.get("target_child_roles")
    return RoleRelationRule(
        kind=str(raw["kind"]),
        room_types=room_types,
        anchor_roles=anchor_roles,
        hard=bool(raw.get("hard", False)),
        weight=raw.get("weight"),
        priority=int(raw.get("priority", 10)),
        via_descendant_of=raw.get("via_descendant_of"),
        target_child_roles=tuple(target) if target else (),
        offset_i=float(raw.get("offset_i", 0.0)),
        offset_j=float(raw.get("offset_j", 0.0)),
        distance_m=float(raw.get("distance_m", 0.7)),
        side=raw.get("side"),
        surface_kind=raw.get("surface_kind"),
        wall=raw.get("wall"),
        additive=bool(raw.get("additive", False)),
    )


@lru_cache(maxsize=1)
def load_relation_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Relation config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def relation_kinds() -> dict[str, RelationKindSpec]:
    data = load_relation_config()
    out: dict[str, RelationKindSpec] = {}
    for name, spec in (data.get("relation_kinds") or {}).items():
        out[name] = RelationKindSpec(
            ip_type=str(spec.get("ip_type", name)),
            side=spec.get("side"),
            default_weight=float(spec.get("default_weight", 8.0)),
        )
    return out


@lru_cache(maxsize=1)
def role_specs() -> dict[str, RoleRelationSpec]:
    data = load_relation_config()
    out: dict[str, RoleRelationSpec] = {}
    for role, body in (data.get("roles") or {}).items():
        rules = [_parse_rule(r) for r in body.get("relations") or []]
        out[role] = RoleRelationSpec(
            is_anchor=bool(body.get("is_anchor", False)),
            relations=rules,
        )
    return out


def catalog_roles() -> set[str]:
    catalog = load_catalog()
    return {a["role"] for a in catalog.get("assets", [])}


def anchor_roles_for_room(room_type: str) -> set[str]:
    return {role for role, _ in ROOM_ANCHOR_SPECS.get(room_type, [])}


def get_rules_for_role(role: str, room_type: str) -> list[RoleRelationRule]:
    spec = role_specs().get(role)
    if not spec:
        return []
    matched: list[RoleRelationRule] = []
    for rule in spec.relations:
        if "*" in rule.room_types or room_type in rule.room_types:
            matched.append(rule)
    return sorted(matched, key=lambda r: r.priority)


def validate_relation_config() -> list[str]:
    """Return validation errors (empty if ok)."""
    errors: list[str] = []
    catalog = catalog_roles()
    specs = role_specs()
    kinds = relation_kinds()

    for role in catalog:
        if role not in specs:
            errors.append(f"missing role entry in relations config: {role}")

    for role, spec in specs.items():
        if role not in catalog:
            errors.append(f"unknown role in relations config: {role}")
        for rule in spec.relations:
            if rule.kind not in kinds:
                errors.append(f"{role}: unknown relation kind '{rule.kind}'")
            all_anchors: set[str] = set()
            for rt in ("bedroom", "living_room", "kitchen"):
                all_anchors |= anchor_roles_for_room(rt)
            for ar in rule.anchor_roles:
                for rt in rule.room_types:
                    if rt == "*":
                        if ar not in all_anchors and ar != role:
                            errors.append(
                                f"{role}: anchor_role '{ar}' not a known anchor"
                            )
                        continue
                    valid = anchor_roles_for_room(rt)
                    if ar not in valid and ar != role:
                        errors.append(
                            f"{role}: anchor_role '{ar}' not in {rt} anchors {valid}"
                        )
    return errors
