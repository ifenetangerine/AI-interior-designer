"""FastAPI pipeline endpoint tests (no network)."""

from fastapi.testclient import TestClient

from colayout.api.app import create_app


def test_health():
    client = TestClient(create_app())
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_pipeline_run_mock_llm():
    client = TestClient(create_app())
    r = client.post(
        "/api/pipeline/run",
        json={
            "room_id": "test_room",
            "type": "bedroom",
            "width_m": 4.0,
            "length_m": 3.5,
            "preferences": "",
            "mock_llm": True,
            "modulor_cell_m": 0.5,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert len(data["layout"]["furniture"]) >= 1
    assert len(data["placements"]) >= 1
    assert data["layout_draft"] is not None
    assert len(data["layout_draft"]["placements"]) >= 1
    assert data["placements"][0]["obj_url"].startswith("/kenney/")
    assert len(data["placements"][0]["footprint_m"]) == 4


def test_pipeline_run_llm_only():
    client = TestClient(create_app())
    r = client.post(
        "/api/pipeline/run",
        json={
            "room_id": "test_room",
            "type": "bedroom",
            "width_m": 4.0,
            "length_m": 3.5,
            "mock_llm": True,
            "placement_mode": "llm_only",
            "modulor_cell_m": 0.5,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["placement_mode"] == "llm_only"
    assert len(data["placements"]) >= 1
    assert data["layout_draft"] is not None
    assert data["anchor_debug"] is not None
    assert len(data["anchor_debug"]["anchors"]) >= 1


def test_catalog():
    client = TestClient(create_app())
    r = client.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    assert "assets" in body
    assert len(body["assets"]) > 0


def test_orientation_labels_api():
    client = TestClient(create_app())
    r = client.get("/api/orientation/models")
    assert r.status_code == 200
    models = r.json()
    assert len(models) > 0
    mid = models[0]["id"]
    r2 = client.put(
        f"/api/orientation/labels/{mid}",
        json={"front_dir": [1.0, 0.0], "wall_anchor": "center"},
    )
    assert r2.status_code == 200
    labels = client.get("/api/orientation/labels").json()
    assert mid in labels["labels"]
    client.delete(f"/api/orientation/labels/{mid}")
