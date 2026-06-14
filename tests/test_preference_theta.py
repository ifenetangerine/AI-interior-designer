"""Preference θ schema and nudge."""

from colayout.preference.theta import (
    apply_theta,
    clamp_theta,
    default_theta,
    nudge_theta,
    sample_theta_pair,
    theta_schema,
)
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
    ThetaMetrics,
)


def test_default_theta_has_globals_and_kinds():
    theta = default_theta("bedroom")
    assert "global.balance" in theta
    assert "global.walk" in theta
    assert "bedroom.kind.adjacent.weight" in theta
    assert "metric.adjacent_gap_m" in theta


def test_theta_schema_tiers():
    schema = theta_schema("living_room")
    tiers = {p.tier for p in schema}
    assert tiers == {"global", "kind", "metric"}


def test_nudge_moves_toward_winner():
    room_type = "bedroom"
    current = default_theta(room_type)
    winner = dict(current)
    loser = dict(current)
    key = "global.balance"
    winner[key] = current[key] + 0.2
    loser[key] = current[key] - 0.2
    nudged = nudge_theta(current, winner, loser, room_type, alpha=0.5)
    assert nudged[key] > current[key]


def test_apply_theta_updates_kind_weight_and_metrics():
    theta = default_theta("living_room")
    theta["living_room.kind.adjacent.weight"] = 20.0
    theta["metric.symmetry_strength"] = 18.0
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="living_room",
        furniture=[
            FurnitureItem(id="a", model_id="tableCoffee", category="coffee_table")
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.ADJACENT,
                furniture_a="a",
                furniture_b="b",
                hard=False,
                weight=8.0,
                rule_key="living_room.coffee_table.adjacent.2",
            )
        ],
    )
    updated = apply_theta(graph, theta)
    c = updated.constraints[0]
    assert c.weight == 20.0
    assert updated.theta_metrics is not None
    assert updated.theta_metrics.symmetry_strength == 18.0


def test_sample_pair_differs():
    current = default_theta("kitchen")
    a, b = sample_theta_pair(current, "kitchen", block_index=1)
    assert a != b or any(a[k] != b[k] for k in a)


def test_clamp_theta_respects_bounds():
    theta = default_theta("bedroom")
    theta["global.balance"] = 99.0
    clamped = clamp_theta(theta, "bedroom")
    assert clamped["global.balance"] <= 0.5


def test_apply_theta_in_front_of_distance_from_metric():
    theta = default_theta("bedroom")
    theta["metric.chair_desk_dist_m"] = 0.85
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[FurnitureItem(id="c", model_id="chair", category="chair")],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.IN_FRONT_OF,
                furniture_a="c",
                furniture_b="desk",
                hard=False,
                weight=10.0,
                distance_m=0.7,
                rule_key="bedroom.chair.in_front_of.1",
            )
        ],
    )
    updated = apply_theta(graph, theta)
    assert updated.constraints[0].distance_m == 0.85
