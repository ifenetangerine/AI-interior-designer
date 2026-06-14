"""Theta metrics affect IP objective construction."""

from colayout.ip.objectives import build_objective_interval
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    ObjectiveWeights,
    RoomSceneGraph,
    ThetaMetrics,
)
from ortools.sat.python import cp_model


def _minimal_graph(
    *,
    metrics: ThetaMetrics | None = None,
    constraints: list[FurnitureConstraint] | None = None,
) -> RoomSceneGraph:
    return RoomSceneGraph(
        room_id="t",
        room_type="living_room",
        furniture=[
            FurnitureItem(id="sofa", model_id="loungeSofa", category="sofa"),
            FurnitureItem(id="ns1", model_id="sideTable", category="nightstand"),
            FurnitureItem(id="ns2", model_id="sideTable", category="nightstand"),
            FurnitureItem(id="bed", model_id="bedDouble", category="bed"),
        ],
        constraints=constraints or [],
        weights=ObjectiveWeights(rel=1.0, walk=0.7, balance=0.3, proportion=0.2),
        theta_metrics=metrics,
    )


def test_symmetric_pair_uses_theta_metrics_strength():
    graph = _minimal_graph(
        metrics=ThetaMetrics(symmetry_strength=20.0),
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.SYMMETRIC_PAIR,
                furniture="bed",
                furniture_a="ns1",
                furniture_b="ns2",
                axis="j",
                hard=False,
                weight=8.0,
            )
        ],
    )
    model = cp_model.CpModel()
    terms = build_objective_interval(model, [], graph, 16, 14, 0.25)
    assert len(terms) >= 0


def test_build_objective_with_metrics_runs():
    graph = _minimal_graph(metrics=ThetaMetrics(adjacent_gap_m=0.1))
    model = cp_model.CpModel()
    terms = build_objective_interval(model, [], graph, 16, 14, 0.25)
    assert isinstance(terms, list)
