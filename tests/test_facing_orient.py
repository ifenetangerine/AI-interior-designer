"""Orientation: chairs face tables; wall pieces face into room."""

import math

from colayout.assets.orientation import yaw_deg_for_placement
from colayout.assets.kenney import load_kenney_catalog
from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_room_with_graph
from colayout.placement.orient import _world_front, apply_facing_orientations, best_orientation
from colayout.schemas.floor import RoomSpec


def _yaw_rad(model_id: str, category: str, orientation: int) -> float:
    catalog = load_kenney_catalog()
    return math.radians(
        yaw_deg_for_placement(catalog, model_id, category, orientation)
    )


def test_chair_orient0_faces_north():
    catalog = load_kenney_catalog()
    fx, fz = _world_front("chairDesk", "chair", 0, catalog)
    assert abs(fx) < 0.01
    assert fz > 0.9


def test_sofa_south_wall_faces_north():
    o = best_orientation("loungeSofa", "sofa", (0.0, 1.0))
    fx, fz = _world_front("loungeSofa", "sofa", o, load_kenney_catalog())
    assert fz > 0.9


def test_llm_refine_desk_chair_and_sofa_orientations():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), modulor_cell_m=0.25, placement_mode="llm_refine"
    )
    catalog = load_kenney_catalog()
    by_id = {f.id: f for f in bundle.placement.furniture}
    desk = by_id["desk"]
    chair = by_id["desk_chair"]
    cfx, cfz = _world_front(chair.model_id, chair.category, chair.orientation, catalog)
    dfx, dfz = _world_front(desk.model_id, desk.category, desk.orientation, catalog)
    tx = desk.centroid_i - chair.centroid_i
    tz = desk.centroid_j - chair.centroid_j
    mag = math.hypot(tx, tz)
    assert mag > 0.1
    ux, uz = tx / mag, tz / mag
    assert cfx * ux + cfz * uz > 0.85
    assert dfx * (-ux) + dfz * (-uz) > 0.85


def test_nightstand_faces_into_room_west_wall_bedroom():
    from colayout.pipeline.place import place_room_with_graph

    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), modulor_cell_m=0.25, placement_mode="llm_refine"
    )
    catalog = load_kenney_catalog()
    bed = next(f for f in bundle.placement.furniture if f.id == "bed")
    for nid in ("nightstand_l", "nightstand_r"):
        ns = next(f for f in bundle.placement.furniture if f.id == nid)
        fx, fz = _world_front(ns.model_id, ns.category, ns.orientation, catalog)
        assert fx > 0.85


def test_living_sofa_faces_away_from_south_wall():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room, MockLLMProvider(), modulor_cell_m=0.25, placement_mode="llm_refine"
    )
    catalog = load_kenney_catalog()
    sofa = next(f for f in bundle.placement.furniture if f.id == "sofa")
    fx, fz = _world_front(sofa.model_id, sofa.category, sofa.orientation, catalog)
    assert fz > 0.85
