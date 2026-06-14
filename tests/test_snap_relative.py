"""Wall snap preserves relative_to offsets (nightstands stay by bed)."""

import math

from colayout.llm.provider import MockLLMProvider
from colayout.llm.snap_placement import snap_placements_to_walls
from colayout.schemas.floor import RoomSpec


def test_nightstands_stay_near_bed_after_wall_snap():
    room = RoomSpec(id="b", type="bedroom", width_m=5.0, length_m=4.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    snapped = snap_placements_to_walls(draft, room)
    by_id = {p.id: p for p in snapped.placements}
    bed = by_id["bed"]
    for nid in ("nightstand_l", "nightstand_r"):
        if nid not in by_id:
            continue
        ns = by_id[nid]
        dist = math.hypot(
            ns.center_x_m - bed.center_x_m,
            ns.center_z_m - bed.center_z_m,
        )
        assert dist < 1.2, f"{nid} drifted {dist:.2f} m from bed"


def test_large_bedroom_nightstands_not_at_room_center():
    room = RoomSpec(id="b", type="bedroom", width_m=6.0, length_m=5.0)
    draft = MockLLMProvider().generate_layout_draft(room)
    by_id = {p.id: p for p in draft.placements}
    bed = by_id["bed"]
    for nid in ("nightstand_l", "nightstand_r"):
        if nid not in by_id:
            continue
        ns = by_id[nid]
        dist = math.hypot(
            ns.center_x_m - bed.center_x_m,
            ns.center_z_m - bed.center_z_m,
        )
        assert dist < 1.5
