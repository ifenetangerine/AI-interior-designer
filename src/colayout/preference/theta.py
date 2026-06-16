"""Tunable relational θ: hierarchical schema, apply, sample, nudge."""

from __future__ import annotations

import random
from dataclasses import dataclass

from colayout.design.principle_registry import COFFEE_SOFA_MAX_M, COFFEE_SOFA_MIN_M
from colayout.relations.loader import relation_kinds
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    ObjectiveWeights,
    RoomSceneGraph,
    ThetaMetrics,
)

WEIGHT_MIN = 1.0
WEIGHT_MAX = 24.0
DISTANCE_MIN = 0.3
DISTANCE_MAX = 1.2
GAP_MAX = 0.3
INSET_MAX = 0.8
ORPHAN_RADIUS_MAX = 3.0

GLOBAL_KEYS: dict[str, tuple[float, float]] = {
    "global.balance": (0.0, 0.5),
    "global.proportion": (0.0, 0.5),
    "global.rhythm": (0.0, 0.3),
    "global.walk": (0.0, 1.0),
    "global.rel": (0.0, 1.0),
}

GLOBAL_DEFAULTS: dict[str, float] = {
    "global.balance": 0.3,
    "global.proportion": 0.2,
    "global.rhythm": 0.1,
    "global.walk": 0.7,
    "global.rel": 1.0,
}

# Relation-kind bundles (ip_type → default weight from relation_kinds.yaml).
KIND_IP_TYPES: tuple[str, ...] = (
    "adjacent",
    "in_front_of",
    "facing",
    "on_top_of",
    "centered_under",
    "against_wall",
    "symmetric_pair",
    "relative_position",
)

CONSTRAINT_TO_KIND: dict[ConstraintType, str] = {
    ConstraintType.ADJACENT: "adjacent",
    ConstraintType.IN_FRONT_OF: "in_front_of",
    ConstraintType.FACING: "facing",
    ConstraintType.ON_TOP_OF: "on_top_of",
    ConstraintType.CENTERED_UNDER: "centered_under",
    ConstraintType.AGAINST_WALL: "against_wall",
    ConstraintType.SYMMETRIC_PAIR: "symmetric_pair",
    ConstraintType.RELATIVE_POSITION: "relative_position",
}

# Room-specific metric params: key → (min, max, default).
METRIC_SPECS: dict[str, tuple[float, float, float]] = {
    "metric.adjacent_gap_m": (0.0, GAP_MAX, 0.0),
    "metric.symmetry_strength": (WEIGHT_MIN, WEIGHT_MAX, 12.0),
    "metric.on_surface_strength": (WEIGHT_MIN, WEIGHT_MAX, 10.0),
    "metric.orphan_radius_m": (1.0, ORPHAN_RADIUS_MAX, 2.0),
    "metric.orphan_weight": (1.0, WEIGHT_MAX, 4.0),
    "metric.door_clearance_min_m": (0.6, 1.2, 0.9),
    "metric.chair_desk_dist_m": (DISTANCE_MIN, DISTANCE_MAX, 0.7),
    "metric.sofa_coffee_dist_m": (COFFEE_SOFA_MIN_M, COFFEE_SOFA_MAX_M, 0.4),
    "metric.sofa_tv_dist_m": (2.0, 5.0, 3.0),
    "metric.bar_stool_dist_m": (DISTANCE_MIN, DISTANCE_MAX, 0.6),
    "metric.wall_inset_sleep_m": (0.0, INSET_MAX, 0.0),
    "metric.wall_inset_seating_m": (0.0, INSET_MAX, 0.0),
    "metric.wall_inset_storage_m": (0.0, INSET_MAX, 0.0),
}

METRICS_BY_ROOM: dict[str, tuple[str, ...]] = {
    "bedroom": (
        "metric.adjacent_gap_m",
        "metric.symmetry_strength",
        "metric.on_surface_strength",
        "metric.orphan_radius_m",
        "metric.orphan_weight",
        "metric.door_clearance_min_m",
        "metric.chair_desk_dist_m",
        "metric.wall_inset_sleep_m",
        "metric.wall_inset_storage_m",
    ),
    "living_room": (
        "metric.adjacent_gap_m",
        "metric.symmetry_strength",
        "metric.on_surface_strength",
        "metric.orphan_radius_m",
        "metric.orphan_weight",
        "metric.door_clearance_min_m",
        "metric.sofa_coffee_dist_m",
        "metric.sofa_tv_dist_m",
        "metric.wall_inset_seating_m",
    ),
    "kitchen": (
        "metric.adjacent_gap_m",
        "metric.symmetry_strength",
        "metric.on_surface_strength",
        "metric.orphan_radius_m",
        "metric.orphan_weight",
        "metric.door_clearance_min_m",
        "metric.bar_stool_dist_m",
        "metric.wall_inset_storage_m",
    ),
}

# rule_key child_role prefix → metric distance key for IN_FRONT_OF.
_DISTANCE_BY_CHILD_ROLE: dict[str, str] = {
    "chair": "metric.chair_desk_dist_m",
    "coffee_table": "metric.sofa_coffee_dist_m",
    "bar_stool": "metric.bar_stool_dist_m",
}


@dataclass(frozen=True)
class ThetaParam:
    key: str
    min_val: float
    max_val: float
    default: float
    tier: str = "metric"


def _kind_default_weight(ip_type: str) -> float:
    kinds = relation_kinds()
    for spec in kinds.values():
        if spec.ip_type == ip_type:
            return float(spec.default_weight)
    return 8.0


def _kind_key(room_type: str, ip_type: str) -> str:
    return f"{room_type}.kind.{ip_type}.weight"


def theta_schema(room_type: str) -> list[ThetaParam]:
    """Hierarchical tunable params: globals + kind bundles + room metrics."""
    params: list[ThetaParam] = []

    for gkey, (lo, hi) in GLOBAL_KEYS.items():
        params.append(
            ThetaParam(
                key=gkey,
                min_val=lo,
                max_val=hi,
                default=GLOBAL_DEFAULTS[gkey],
                tier="global",
            )
        )

    for ip_type in KIND_IP_TYPES:
        default_w = _kind_default_weight(ip_type)
        params.append(
            ThetaParam(
                key=_kind_key(room_type, ip_type),
                min_val=WEIGHT_MIN,
                max_val=WEIGHT_MAX,
                default=default_w,
                tier="kind",
            )
        )

    for mkey in METRICS_BY_ROOM.get(room_type, METRICS_BY_ROOM["bedroom"]):
        lo, hi, default = METRIC_SPECS[mkey]
        params.append(
            ThetaParam(
                key=mkey,
                min_val=lo,
                max_val=hi,
                default=default,
                tier="metric",
            )
        )

    return params


def default_theta(room_type: str) -> dict[str, float]:
    return {p.key: p.default for p in theta_schema(room_type)}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def clamp_theta(theta: dict[str, float], room_type: str) -> dict[str, float]:
    bounds = {p.key: (p.min_val, p.max_val) for p in theta_schema(room_type)}
    out = dict(default_theta(room_type))
    out.update(theta)
    for key, val in list(out.items()):
        if key in bounds:
            lo, hi = bounds[key]
            out[key] = _clamp(float(val), lo, hi)
    return out


def _child_role_from_rule_key(rule_key: str | None) -> str | None:
    if not rule_key:
        return None
    parts = rule_key.split(".")
    if len(parts) >= 2:
        return parts[1]
    return None


def canonical_distance_for_constraint(
    c: FurnitureConstraint,
    room_type: str,
    theta: dict[str, float],
) -> float | None:
    """Map IN_FRONT_OF constraint to metric target distance when applicable."""
    if c.type != ConstraintType.IN_FRONT_OF:
        return None
    child_role = _child_role_from_rule_key(c.rule_key)
    if child_role and child_role in _DISTANCE_BY_CHILD_ROLE:
        mkey = _DISTANCE_BY_CHILD_ROLE[child_role]
        if mkey in theta:
            return float(theta[mkey])
    return None


def _theta_metrics_from_theta(theta: dict[str, float], room_type: str) -> ThetaMetrics:
    clamped = clamp_theta(theta, room_type)
    kwargs: dict = {
        "adjacent_gap_m": clamped.get("metric.adjacent_gap_m", 0.0),
        "symmetry_strength": clamped.get("metric.symmetry_strength", 12.0),
        "on_surface_strength": clamped.get("metric.on_surface_strength", 10.0),
        "orphan_radius_m": clamped.get("metric.orphan_radius_m", 2.0),
        "orphan_weight": clamped.get("metric.orphan_weight", 4.0),
        "door_clearance_min_m": clamped.get("metric.door_clearance_min_m", 0.9),
    }
    if room_type == "bedroom":
        kwargs["chair_desk_dist_m"] = clamped.get("metric.chair_desk_dist_m")
        kwargs["wall_inset_sleep_m"] = clamped.get("metric.wall_inset_sleep_m")
        kwargs["wall_inset_storage_m"] = clamped.get("metric.wall_inset_storage_m")
    elif room_type == "living_room":
        kwargs["sofa_coffee_dist_m"] = clamped.get("metric.sofa_coffee_dist_m")
        kwargs["sofa_tv_dist_m"] = clamped.get("metric.sofa_tv_dist_m")
        kwargs["wall_inset_seating_m"] = clamped.get("metric.wall_inset_seating_m")
    elif room_type == "kitchen":
        kwargs["bar_stool_dist_m"] = clamped.get("metric.bar_stool_dist_m")
        kwargs["wall_inset_storage_m"] = clamped.get("metric.wall_inset_storage_m")
    return ThetaMetrics(**kwargs)


def _kind_weight_for_constraint(
    c: FurnitureConstraint,
    room_type: str,
    theta: dict[str, float],
) -> float | None:
    kind = CONSTRAINT_TO_KIND.get(c.type)
    if not kind:
        return None
    kkey = _kind_key(room_type, kind)
    return theta.get(kkey)


def load_room_theta(room_type: str) -> dict[str, float]:
    """Load clamped relational θ for a room type from theta_state.json."""
    from colayout.preference.store import get_room_theta_state

    raw = get_room_theta_state(room_type)
    return clamp_theta(raw.get("theta_current", {}), room_type)


def apply_theta(graph: RoomSceneGraph, theta: dict[str, float]) -> RoomSceneGraph:
    """Apply kind-bundle weights, metric targets, and global objectives."""
    room_type = graph.room_type
    theta = clamp_theta(theta, room_type)
    metrics = _theta_metrics_from_theta(theta, room_type)

    stack_types = frozenset(
        {ConstraintType.ON_TOP_OF, ConstraintType.UNDER}
    )
    new_constraints = []
    for c in graph.constraints:
        if c.type in stack_types:
            new_constraints.append(c)
            continue
        updates: dict = {}
        kw = _kind_weight_for_constraint(c, room_type, theta)
        if kw is not None:
            updates["weight"] = kw
        if c.type == ConstraintType.IN_FRONT_OF:
            dist = canonical_distance_for_constraint(c, room_type, theta)
            if dist is not None:
                updates["distance_m"] = dist
        new_constraints.append(
            c.model_copy(update=updates) if updates else c
        )

    w = graph.weights.model_copy()
    if "global.balance" in theta:
        w.balance = theta["global.balance"]
    if "global.proportion" in theta:
        w.proportion = theta["global.proportion"]
    if "global.rhythm" in theta:
        w.rhythm = theta["global.rhythm"]
    if "global.walk" in theta:
        w.walk = theta["global.walk"]
    if "global.rel" in theta:
        w.rel = theta["global.rel"]

    return graph.model_copy(
        update={
            "constraints": new_constraints,
            "weights": w,
            "theta_metrics": metrics,
        }
    )


def nudge_theta(
    theta_current: dict[str, float],
    theta_winner: dict[str, float],
    theta_loser: dict[str, float],
    room_type: str,
    *,
    alpha: float = 0.15,
) -> dict[str, float]:
    base = clamp_theta(theta_current, room_type)
    winner = clamp_theta(theta_winner, room_type)
    loser = clamp_theta(theta_loser, room_type)
    out = dict(base)
    for key in out:
        out[key] = base[key] + alpha * (winner[key] - loser[key])
    return clamp_theta(out, room_type)


_BLOCK_ORDER = ("global", "kind", "metric")
EXPLORATION_SIGMA = 0.04


def _exploration_jitter(
    theta: dict[str, float],
    schema: list[ThetaParam],
    rng: random.Random,
    *,
    key_count: int | None = None,
    sigma: float = EXPLORATION_SIGMA,
) -> dict[str, float]:
    """Small Gaussian noise so A/B (and tie steps) do not collapse to identical θ."""
    out = dict(theta)
    keys = [p.key for p in schema]
    rng.shuffle(keys)
    n = key_count or max(3, len(keys) // 5)
    for key in keys[:n]:
        param = next(p for p in schema if p.key == key)
        span = param.max_val - param.min_val
        out[key] = _clamp(
            out[key] + rng.gauss(0.0, span * sigma),
            param.min_val,
            param.max_val,
        )
    return out


def explore_theta(
    theta_current: dict[str, float],
    room_type: str,
    *,
    rng: random.Random | None = None,
) -> dict[str, float]:
    """Random walk on θ after a tie — keeps exploring without directional nudge."""
    rng = rng or random.Random()
    schema = theta_schema(room_type)
    base = clamp_theta(theta_current, room_type)
    jittered = _exploration_jitter(base, schema, rng, key_count=4, sigma=0.06)
    return clamp_theta(jittered, room_type)


def sample_theta_pair(
    theta_current: dict[str, float],
    room_type: str,
    *,
    rng: random.Random | None = None,
    block_index: int | None = None,
    keys_per_block: int = 3,
) -> tuple[dict[str, float], dict[str, float]]:
    """Sample two θ vectors by perturbing one schema block (global/kind/metric)."""
    rng = rng or random.Random()
    schema = theta_schema(room_type)
    current = clamp_theta(theta_current, room_type)

    by_tier: dict[str, list[ThetaParam]] = {t: [] for t in _BLOCK_ORDER}
    for p in schema:
        by_tier.setdefault(p.tier, []).append(p)

    if block_index is None:
        block_index = rng.randint(0, len(_BLOCK_ORDER) - 1)
    tier = _BLOCK_ORDER[block_index % len(_BLOCK_ORDER)]
    pool = by_tier.get(tier, [])
    if len(pool) < 2:
        pool = schema

    keys = [p.key for p in pool]
    rng.shuffle(keys)
    pick = keys[: min(keys_per_block, len(keys))]

    theta_a = dict(current)
    theta_b = dict(current)
    for key in pick:
        param = next(p for p in schema if p.key == key)
        span = param.max_val - param.min_val
        delta = max(0.05, span * 0.15)
        sign = rng.choice([-1.0, 1.0])
        theta_a[key] = _clamp(
            current[key] + sign * delta, param.min_val, param.max_val
        )
        theta_b[key] = _clamp(
            current[key] - sign * delta, param.min_val, param.max_val
        )

    theta_a = clamp_theta(
        _exploration_jitter(theta_a, schema, rng, key_count=2), room_type
    )
    theta_b = clamp_theta(
        _exploration_jitter(theta_b, schema, rng, key_count=2), room_type
    )
    if not any(theta_a[k] != theta_b[k] for k in theta_a) and pick:
        key = pick[0]
        param = next(p for p in schema if p.key == key)
        span = param.max_val - param.min_val
        bump = max(0.08, span * 0.12)
        theta_b[key] = _clamp(theta_b[key] + bump, param.min_val, param.max_val)
        theta_b = clamp_theta(theta_b, room_type)

    return theta_a, theta_b


def objective_weights_from_theta(theta: dict[str, float]) -> ObjectiveWeights:
    return ObjectiveWeights(
        rel=theta.get("global.rel", GLOBAL_DEFAULTS["global.rel"]),
        bal=0.0,
        walk=theta.get("global.walk", GLOBAL_DEFAULTS["global.walk"]),
        balance=theta.get("global.balance", GLOBAL_DEFAULTS["global.balance"]),
        proportion=theta.get("global.proportion", GLOBAL_DEFAULTS["global.proportion"]),
        rhythm=theta.get("global.rhythm", GLOBAL_DEFAULTS["global.rhythm"]),
    )


def schema_payload_grouped(room_type: str) -> list[dict]:
    return [
        {
            "key": p.key,
            "min": p.min_val,
            "max": p.max_val,
            "default": p.default,
            "tier": p.tier,
        }
        for p in theta_schema(room_type)
    ]
