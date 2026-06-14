"""Tests for furniture_role → model_id resolution."""

from colayout.catalog.resolve_model import (
    catalog_roles_prompt_json,
    infer_lamp_surface,
    intent_from_model_id,
    resolve_model_from_intent,
)
from colayout.llm.draft_from_llm import room_layout_draft_from_llm_data
from colayout.schemas.floor import RoomSpec


def test_resolve_lamp_table_vs_floor():
    table = resolve_model_from_intent(
        placement_id="lamp_1",
        furniture_role="lamp",
        room_type="bedroom",
        surface="table",
    )
    floor = resolve_model_from_intent(
        placement_id="lamp_2",
        furniture_role="lamp",
        room_type="bedroom",
        surface="floor",
    )
    assert table
    assert floor
    assert table != floor


def test_resolve_hallucinated_role_alias():
    mid = resolve_model_from_intent(
        placement_id="chair_1",
        furniture_role="reading_chair",
        room_type="living_room",
    )
    assert mid
    from colayout.catalog.kenney_index import role_for_model

    assert role_for_model(mid) == "chair"


def test_resolve_tv_console_virtual_role():
    mid = resolve_model_from_intent(
        placement_id="tv_console",
        furniture_role="tv_console",
        room_type="living_room",
    )
    assert mid == "sideTable"


def test_infer_lamp_surface_from_on_surface_of():
    row = {"on_surface_of": "nightstand_1", "furniture_role": "lamp"}
    assert infer_lamp_surface(row) == "table"


def test_intent_from_model_id_round_trip():
    intent = intent_from_model_id("lampSquareTable")
    assert intent["furniture_role"] == "lamp"
    assert intent["surface"] == "table"


def test_room_layout_draft_from_llm_data_resolves_roles():
    room = RoomSpec(id="b1", type="bedroom", width_m=4.0, length_m=3.5)
    data = {
        "room_id": "b1",
        "room_type": "bedroom",
        "placements": [
            {
                "id": "bed",
                "furniture_role": "bed",
                "placement_order": 1,
                "center_x_m": 1.0,
                "center_z_m": 1.5,
                "orientation": 0,
                "composition_role": "anchor",
            },
            {
                "id": "lamp_1",
                "furniture_role": "lamp",
                "surface": "table",
                "placement_order": 2,
                "center_x_m": 0.5,
                "center_z_m": 1.5,
                "orientation": 0,
                "relative_to": "bed",
                "on_surface_of": "ns1",
            },
        ],
    }
    draft, errors = room_layout_draft_from_llm_data(data, room)
    assert draft.placements
    assert all(p.model_id for p in draft.placements)
    assert not any("unknown model_id" in e for e in errors)


def test_catalog_roles_prompt_has_no_raw_model_ids():
    blob = catalog_roles_prompt_json("bedroom")
    assert "bedDouble" not in blob
    assert "furniture_roles" in blob
