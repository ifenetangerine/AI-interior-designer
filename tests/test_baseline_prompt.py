"""Tests for catalog injection into LLM placement prompts."""

import json

from colayout.catalog.kenney_index import catalog_for_room
from colayout.llm.placement_messages import build_placement_user_message
from colayout.schemas.floor import RoomSpec


def test_catalog_for_room_includes_full_catalog():
    bedroom = catalog_for_room("bedroom")
    kitchen = catalog_for_room("kitchen")
    assert len(bedroom) > 10
    ids = {r["id"] for r in bedroom}
    assert "bedDouble" in ids
    assert "kitchenStove" in ids
    assert {r["id"] for r in kitchen} == ids


def test_build_placement_message_includes_catalog_json():
    room = RoomSpec(
        id="bed1",
        type="bedroom",
        width_m=4.0,
        length_m=3.5,
        preferences="add desk and chair",
    )
    msg = build_placement_user_message(room)
    assert "Kenney catalog" in msg
    assert "add desk and chair" in msg
    assert "Floor area:" in msg
    assert "bedDouble" in msg
    chunk = msg.split("Kenney catalog (pick model_id from this list):\n")[1]
    catalog_json = chunk.split("\n---\n")[0]
    parsed = json.loads(catalog_json)
    assert isinstance(parsed, dict)
    functional = parsed.get("Functional", [])
    assert any(row["id"] == "bedDouble" for row in functional)


def test_build_placement_message_kitchen_has_counter_modules():
    room = RoomSpec(id="k1", type="kitchen", width_m=4.0, length_m=3.0)
    msg = build_placement_user_message(room)
    assert "kitchenBar" in msg
    assert "kitchenStove" in msg
