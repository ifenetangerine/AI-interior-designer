"""Validation locks footprints from catalog."""

from colayout.llm.validate import validate_and_sanitize
from colayout.catalog.kenney_index import footprint_for_model
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import FurnitureItem, RoomSceneGraph


def test_footprint_locked_from_catalog():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[
            FurnitureItem(
                id="bed",
                model_id="bedDouble",
                width_m=99.0,
                length_m=99.0,
            ),
        ],
        constraints=[],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    sanitized, _ = validate_and_sanitize(graph, room)
    exp_w, exp_d = footprint_for_model("bedDouble")
    assert sanitized.furniture[0].width_m == exp_w
    assert sanitized.furniture[0].length_m == exp_d
    assert sanitized.furniture[0].model_id == "bedDouble"


def test_legacy_category_resolves_to_default_model():
    graph = RoomSceneGraph(
        room_id="r1",
        room_type="bedroom",
        furniture=[FurnitureItem(id="bed", category="bed")],
        constraints=[],
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    sanitized, _ = validate_and_sanitize(graph, room)
    assert sanitized.furniture[0].model_id == "bedDouble"
