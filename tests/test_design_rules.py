"""Tests for category normalization and constraint enrichment."""

from colayout.llm.design_rules import enrich_scene_graph, normalize_category
from colayout.llm.validate import validate_and_sanitize
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def test_normalize_rejects_fan():
    assert normalize_category("fan") == "side_table"


def test_validate_strips_unknown_model():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="fan1", model_id="not_a_real_model"),
            FurnitureItem(id="bed", model_id="bedDouble"),
        ],
        constraints=[],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    sanitized, errors = validate_and_sanitize(graph, room)
    assert len(sanitized.furniture) == 1
    assert sanitized.furniture[0].id == "bed"
    assert any("unknown model_id" in e for e in errors)


def test_enrich_adds_bed_against_wall():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[FurnitureItem(id="bed", model_id="bedDouble")],
        constraints=[],
    )
    enriched = enrich_scene_graph(graph)
    walls = [
        c.wall
        for c in enriched.constraints
        if c.type == ConstraintType.AGAINST_WALL
    ]
    assert "west" in walls
    assert enriched.weights.bal <= 0.05
    assert enriched.weights.walk >= 0.6
