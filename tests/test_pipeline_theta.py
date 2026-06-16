"""Pipeline loads relational θ from theta_state.json for CSP refine."""

import json

from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_room_with_graph
from colayout.preference.theta import default_theta, load_room_theta
from colayout.schemas.floor import RoomSpec


def test_load_room_theta_from_state_file(tmp_path, monkeypatch):
    state_path = tmp_path / "theta_state.json"
    monkeypatch.setattr("colayout.preference.store.THETA_STATE_PATH", state_path)
    custom_walk = 0.42
    state_path.write_text(
        json.dumps(
            {
                "room_types": {
                    "bedroom": {
                        "theta_current": {
                            **default_theta("bedroom"),
                            "global.walk": custom_walk,
                        },
                        "comparison_count": 5,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    theta = load_room_theta("bedroom")
    assert theta["global.walk"] == custom_walk


def test_llm_refine_pipeline_applies_theta_state(tmp_path, monkeypatch):
    state_path = tmp_path / "theta_state.json"
    monkeypatch.setattr("colayout.preference.store.THETA_STATE_PATH", state_path)
    custom_walk = 0.88
    state_path.write_text(
        json.dumps(
            {
                "room_types": {
                    "bedroom": {
                        "theta_current": {
                            **default_theta("bedroom"),
                            "global.walk": custom_walk,
                            "metric.door_clearance_min_m": 1.1,
                        },
                        "comparison_count": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(
        room,
        MockLLMProvider(),
        modulor_cell_m=0.5,
        placement_mode="llm_refine",
        time_limit_s=10.0,
    )
    assert bundle is not None
    assert bundle.scene_graph.weights.walk == custom_walk
    assert bundle.scene_graph.theta_metrics is not None
    assert bundle.scene_graph.theta_metrics.door_clearance_min_m == 1.1
