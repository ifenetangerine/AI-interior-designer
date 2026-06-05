"""Room architecture schema and prompt integration."""

from colayout.design.principle_registry import placement_guidance_for_room
from colayout.schemas.architecture import RoomArchitecture, default_architecture
from colayout.schemas.floor import RoomSpec


def test_default_architecture_living():
    arch = default_architecture("living_room", 4.0, 3.5)
    assert arch.door_wall == "south"
    assert arch.focal_wall == "north"
    assert arch.focal_center_z_m == 3.5


def test_architecture_in_placement_guidance():
    room = RoomSpec(
        id="r1",
        type="living_room",
        width_m=4.0,
        length_m=3.5,
        architecture=RoomArchitecture(
            door_wall="west",
            door_offset_m=1.0,
            focal_wall="north",
            focal_center_x_m=2.0,
            focal_center_z_m=3.5,
        ),
    )
    text = placement_guidance_for_room(room)
    assert "Door on west wall" in text
    assert "Focal emphasis" in text
    assert "Classical design principles" in text
