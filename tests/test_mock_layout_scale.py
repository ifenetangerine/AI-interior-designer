"""Mock layouts scale to the requested room size."""

from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import RoomSpec


def test_kitchen_counters_touch_north_wall_after_refine():
    room = RoomSpec(id="k1", type="kitchen", width_m=6.0, length_m=5.0)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), 0.25, placement_mode="llm_refine"
    )
    assert bundle is not None
    cell = bundle.placement.modulor_cell_m
    counters = [
        f
        for f in bundle.placement.furniture
        if f.category == "counter" and f.stack_parent_id is None
    ]
    assert counters
    for counter in counters:
        north_edge_z = (counter.origin_j + counter.length_cells) * cell
        assert north_edge_z >= room.length_m - cell * 0.5


def test_kitchen_counters_near_north_wall_on_large_room():
    room = RoomSpec(id="k1", type="kitchen", width_m=6.0, length_m=5.0)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), 0.25, placement_mode="llm_only"
    )
    assert bundle is not None
    cell = bundle.placement.modulor_cell_m
    bar = next(f for f in bundle.placement.furniture if f.id == "bar_end")
    z1 = (bar.origin_j + bar.length_cells) * cell
    assert z1 >= room.length_m - 0.5


def test_bed_near_west_wall():
    room = RoomSpec(id="b1", type="bedroom", width_m=5.0, length_m=4.0)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), 0.25, placement_mode="llm_only"
    )
    assert bundle is not None
    cell = bundle.placement.modulor_cell_m
    bed = next(f for f in bundle.placement.furniture if f.id == "bed")
    x0 = bed.origin_i * cell
    assert x0 <= 0.25
