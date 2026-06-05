"""Wall-anchoring guidance for the placement LLM."""

from colayout.llm.room_program import placement_wall_guidance
from colayout.schemas.floor import RoomSpec


def test_placement_wall_guidance_includes_anchor_wall():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    text = placement_wall_guidance(room)
    assert "west" in text.lower()
    assert "anchor" in text.lower()
    assert "4.0" in text
    assert "required" in text.lower()


def test_kitchen_guidance_north_wall_counters():
    room = RoomSpec(id="k1", type="kitchen", width_m=5.0, length_m=4.0)
    text = placement_wall_guidance(room)
    assert "north" in text.lower()
    assert "counter" in text.lower()
