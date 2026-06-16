"""TV must stay on_surface_of console through validate and IP stack."""

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import draft_to_scene_graph
from colayout.llm.validate_placement import validate_layout_draft
from colayout.pipeline.place import place_room_with_graph
from colayout.llm.provider import MockLLMProvider
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft
from colayout.schemas.scene import ConstraintType


def test_validate_keeps_tv_on_console_when_offset():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft(
        room_id="lr",
        room_type="living_room",
        placements=[
            FurniturePlacementDraft(
                id="tv",
                model_id="televisionModern",
                placement_order=1,
                center_x_m=2.0,
                center_z_m=3.2,
                orientation=0,
                composition_role="anchor",
                on_surface_of="tv_console",
            ),
            FurniturePlacementDraft(
                id="tv_console",
                model_id="sideTable",
                placement_order=2,
                center_x_m=2.0,
                center_z_m=3.0,
                orientation=0,
                relative_to="tv",
            ),
        ],
    )
    sanitized, _ = validate_layout_draft(draft, room)
    tv = next(p for p in sanitized.placements if p.id == "tv")
    console = next(p for p in sanitized.placements if p.id == "tv_console")
    assert tv.on_surface_of == "tv_console"
    assert tv.center_x_m == console.center_x_m
    assert tv.center_z_m == console.center_z_m

    graph = draft_to_scene_graph(sanitized, room)
    stack = [
        c
        for c in graph.constraints
        if c.type == ConstraintType.ON_TOP_OF and c.furniture_a == "tv"
    ]
    assert stack
    assert stack[0].furniture_b == "tv_console"


def test_living_room_pipeline_tv_has_stack_parent():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room,
        MockLLMProvider(),
        modulor_cell_m=0.25,
        placement_mode="llm_refine",
    )
    assert bundle is not None
    tv = next(f for f in bundle.placement.furniture if f.id == "tv")
    assert tv.stack_parent_id == "tv_console"
    assert tv.stack_mode == "on_top"
