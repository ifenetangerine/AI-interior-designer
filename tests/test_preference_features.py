"""Layout feature extraction."""

from colayout.llm.mock_layouts import load_mock_layout
from colayout.llm.provider import MockLLMProvider
from colayout.preference.features import FEATURE_NAMES, extract_features
from colayout.preference.place import place_from_draft_with_theta
from colayout.preference.theta import default_theta
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft


def test_extract_features_keys():
    room = RoomSpec(id="r1", type="bedroom", width_m=4.0, length_m=3.5)
    draft = RoomLayoutDraft.model_validate(
        {**load_mock_layout(room), "room_id": "r1", "room_type": "bedroom"}
    )
    result = place_from_draft_with_theta(room, draft, default_theta("bedroom"))
    assert result is not None
    feats = extract_features(result.placement, result.scene_graph, room)
    for name in FEATURE_NAMES:
        assert name in feats
    assert isinstance(feats["orphan_count"], float)
