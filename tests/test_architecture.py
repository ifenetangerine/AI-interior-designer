"""Room architecture schema and prompt integration."""

from colayout.design.principle_registry import placement_guidance_for_room
from colayout.schemas.architecture import RoomArchitecture, default_architecture
from colayout.schemas.floor import RoomSpec


def test_default_architecture_living():
    arch = default_architecture("living_room", 4.0, 3.5)
    assert arch.door_wall == "south"
    assert arch.door_offset_m == 1.55
    assert arch.door_width_m == 0.9


def test_architecture_in_placement_guidance():
    room = RoomSpec(
        id="r1",
        type="living_room",
        width_m=4.0,
        length_m=3.5,
        architecture=RoomArchitecture(
            door_wall="west",
            door_offset_m=1.0,
        ),
    )
    text = placement_guidance_for_room(room)
    assert "Door on west wall" in text
    assert "Focal emphasis" not in text
    assert "Classical design principles" in text
