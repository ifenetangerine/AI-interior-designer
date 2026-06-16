"""Few-shot LLM design prompt formatting."""

import json

from colayout.llm.few_shot import (
    few_shot_golden_ids,
    format_few_shot_block,
    load_few_shot_examples,
)
from colayout.schemas.floor import RoomSpec


def _write_llm_design(path, *, design_id, room_type, width_m, length_m, placements):
    path.write_text(
        json.dumps(
            {
                "design_id": design_id,
                "room_type": room_type,
                "width_m": width_m,
                "length_m": length_m,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "draft": {
                    "room_id": design_id,
                    "room_type": room_type,
                    "placements": placements,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_format_few_shot_empty_without_designs(tmp_path, monkeypatch):
    monkeypatch.setattr("colayout.preference.llm_designs.LLM_DESIGNS_DIR", tmp_path)
    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    assert format_few_shot_block(room) == ""


def test_format_few_shot_includes_placements(tmp_path, monkeypatch):
    monkeypatch.setattr("colayout.preference.llm_designs.LLM_DESIGNS_DIR", tmp_path)
    _write_llm_design(
        tmp_path / "bedroom_01.json",
        design_id="bedroom_01",
        room_type="bedroom",
        width_m=4.0,
        length_m=3.5,
        placements=[
            {
                "id": "bed",
                "model_id": "bedDouble",
                "placement_order": 1,
                "center_x_m": 1.0,
                "center_z_m": 1.5,
                "orientation": 0,
                "composition_role": "anchor",
                "zone": "sleep",
            }
        ],
    )
    examples = load_few_shot_examples("bedroom")
    assert len(examples) == 1
    block = format_few_shot_block(
        RoomSpec(id="b2", type="bedroom", width_m=5.0, length_m=4.0)
    )
    assert "Few-shot reference" in block
    assert '"id": "bed"' in block or '"id":"bed"' in block


def test_few_shot_excludes_target_design(tmp_path, monkeypatch):
    monkeypatch.setattr("colayout.preference.llm_designs.LLM_DESIGNS_DIR", tmp_path)
    _write_llm_design(
        tmp_path / "bedroom_01.json",
        design_id="bedroom_01",
        room_type="bedroom",
        width_m=4.0,
        length_m=3.5,
        placements=[
            {
                "id": "bed",
                "model_id": "bedDouble",
                "placement_order": 1,
                "center_x_m": 1.0,
                "center_z_m": 1.5,
                "orientation": 0,
            }
        ],
    )
    assert few_shot_golden_ids("bedroom", exclude_ids={"bedroom_01"}) == []


def test_few_shot_loads_real_cached_designs():
    examples = load_few_shot_examples("living_room")
    assert len(examples) >= 1
    assert all(ex["room_type"] == "living_room" for ex in examples)
    assert all(ex["placements"] for ex in examples)
