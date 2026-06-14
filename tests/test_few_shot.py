"""Few-shot golden layout prompt formatting."""

from colayout.llm.few_shot import (
    few_shot_golden_ids,
    format_few_shot_block,
    load_few_shot_examples,
)
from colayout.preference.store import save_golden_layout
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def test_format_few_shot_empty_without_goldens(tmp_path, monkeypatch):
    monkeypatch.setattr("colayout.preference.store.GOLDEN_DIR", tmp_path)
    room = RoomSpec(id="b", type="bedroom", width_m=4.0, length_m=3.5)
    assert format_few_shot_block(room) == ""


def test_format_few_shot_includes_placements(tmp_path, monkeypatch):
    monkeypatch.setattr("colayout.preference.store.GOLDEN_DIR", tmp_path)
    draft = RoomLayoutDraft(
        room_id="g1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=1.0,
                center_z_m=1.5,
                composition_role="anchor",
                zone="sleep",
            )
        ],
    )
    save_golden_layout(
        "g1",
        label="Test bedroom",
        room_type="bedroom",
        width_m=4.0,
        length_m=3.5,
        draft=draft,
        few_shot=True,
    )
    examples = load_few_shot_examples("bedroom")
    assert len(examples) == 1
    block = format_few_shot_block(
        RoomSpec(id="b2", type="bedroom", width_m=5.0, length_m=4.0)
    )
    assert "Few-shot reference" in block
    assert '"id": "bed"' in block or '"id":"bed"' in block


def test_few_shot_excludes_target_golden(tmp_path, monkeypatch):
    monkeypatch.setattr("colayout.preference.store.GOLDEN_DIR", tmp_path)
    draft = RoomLayoutDraft(
        room_id="g1",
        room_type="bedroom",
        placements=[
            FurniturePlacementDraft(
                id="bed",
                model_id="bedDouble",
                placement_order=1,
                center_x_m=1.0,
                center_z_m=1.5,
            )
        ],
    )
    save_golden_layout(
        "g1",
        label="One",
        room_type="bedroom",
        width_m=4.0,
        length_m=3.5,
        draft=draft,
        few_shot=True,
    )
    assert few_shot_golden_ids("bedroom", exclude_ids={"g1"}) == []
