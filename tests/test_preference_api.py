"""Golden layout and preference API."""

import pytest
from fastapi.testclient import TestClient

from colayout.api.app import create_app
from colayout.llm.mock_layouts import load_mock_layout
from colayout.preference.llm_designs import generate_and_cache_design
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft


@pytest.fixture
def client(tmp_path, monkeypatch):
    golden_dir = tmp_path / "golden_layouts"
    golden_dir.mkdir()
    comp = tmp_path / "preference" / "comparisons.jsonl"
    comp.parent.mkdir(parents=True)
    state = tmp_path / "preference" / "theta_state.json"
    llm_dir = tmp_path / "preference" / "llm_designs"
    llm_dir.mkdir(parents=True)
    monkeypatch.setattr("colayout.preference.store.GOLDEN_DIR", golden_dir)
    monkeypatch.setattr("colayout.preference.store.COMPARISONS_PATH", comp)
    monkeypatch.setattr("colayout.preference.store.THETA_STATE_PATH", state)
    monkeypatch.setattr("colayout.preference.llm_designs.LLM_DESIGNS_DIR", llm_dir)
    return TestClient(create_app())


def _sample_draft():
    room = RoomSpec(id="g1", type="bedroom", width_m=4.0, length_m=3.5)
    data = load_mock_layout(room)
    return RoomLayoutDraft.model_validate(
        {**data, "room_id": "g1", "room_type": "bedroom"}
    )


def test_golden_crud(client):
    draft = _sample_draft()
    res = client.post(
        "/api/golden-layouts",
        json={
            "id": "test_bedroom",
            "label": "Test bedroom",
            "room_type": "bedroom",
            "width_m": 4.0,
            "length_m": 3.5,
            "draft": draft.model_dump(),
        },
    )
    assert res.status_code == 200
    listed = client.get("/api/golden-layouts").json()["layouts"]
    assert any(x["id"] == "test_bedroom" for x in listed)
    got = client.get("/api/golden-layouts/test_bedroom")
    assert got.status_code == 200


def test_preference_state(client):
    res = client.get("/api/preference/state?room_type=bedroom")
    assert res.status_code == 200
    data = res.json()
    assert "theta_current" in data
    assert data["phase"] == "A"


def test_llm_design_list_and_pair_by_room_type(client):
    room = RoomSpec(id="bedroom_01", type="bedroom", width_m=4.0, length_m=3.5)
    cached = generate_and_cache_design("bedroom_01", room, use_mock=True)
    assert cached["design_id"] == "bedroom_01"
    assert cached["draft"]["placements"]

    listed = client.get("/api/preference/llm-designs?room_type=bedroom").json()
    designs = listed["designs"]
    assert any(d["design_id"] == "bedroom_01" for d in designs)
    assert "progress" not in designs[0]

    pair = client.post(
        "/api/preference/pair",
        json={"room_type": "bedroom"},
    )
    assert pair.status_code == 200
    body = pair.json()
    assert body["design_id"] == "bedroom_01"
    assert body["placements_A"]
    assert body["placements_B"]
    assert "progress" not in body
