"""Tests for scene graph validation and sanitization."""

from colayout.llm.validate import validate_and_sanitize
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def test_drops_constraint_with_unknown_id():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="bed", model_id="bedDouble"),
        ],
        constraints=[
            FurnitureConstraint(
                type=ConstraintType.FACING,
                furniture_a="bed",
                furniture_b="missing",
            ),
        ],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    sanitized, errors = validate_and_sanitize(graph, room)
    assert len(sanitized.furniture) == 1
    assert not any(c.furniture_b == "missing" for c in sanitized.constraints)
    assert any(
        c.type == ConstraintType.AGAINST_WALL and c.furniture == "bed"
        for c in sanitized.constraints
    )
    assert any("unknown" in e for e in errors)


def test_floor_coverage_blocking():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id=f"bed_{i}", model_id="bedDouble")
            for i in range(8)
        ],
        constraints=[],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=2.0, length_m=2.0)
    _, errors = validate_and_sanitize(graph, room)
    assert any("exceeds" in e for e in errors)


def test_deduplicate_furniture_ids():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(id="bed", model_id="bedDouble"),
            FurnitureItem(id="bed", model_id="bedSingle"),
        ],
        constraints=[],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    sanitized, errors = validate_and_sanitize(graph, room)
    assert len(sanitized.furniture) == 1
    assert any("duplicate" in e for e in errors)
