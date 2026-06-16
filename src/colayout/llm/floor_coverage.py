"""Floor coverage ratio (FCR) metrics for layout drafts."""

from __future__ import annotations

from colayout.llm.draft_to_hints import footprint_m_for_placement
from colayout.llm.room_program import FCR_MAX, FCR_MIN, floor_coverage_ratio_bounds, room_area_m2
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def floor_footprint_m2(placements: list[FurniturePlacementDraft]) -> float:
    """Sum oriented footprint area for pieces that occupy floor cells."""
    total = 0.0
    for p in placements:
        if p.on_surface_of:
            continue
        w, d = footprint_m_for_placement(p)
        total += w * d
    return total


def draft_floor_coverage_ratio(draft: RoomLayoutDraft, room: RoomSpec) -> float:
    area = room_area_m2(room)
    if area <= 0:
        return 0.0
    return floor_footprint_m2(draft.placements) / area


def draft_floor_coverage_m2(draft: RoomLayoutDraft, room: RoomSpec) -> float:
    return floor_footprint_m2(draft.placements)


def is_draft_underfurnished(
    draft: RoomLayoutDraft,
    room: RoomSpec,
    *,
    min_ratio: float = FCR_MIN,
) -> bool:
    return draft_floor_coverage_ratio(draft, room) < min_ratio - 1e-6


def coverage_deficit_m2(draft: RoomLayoutDraft, room: RoomSpec) -> float:
    """Floor footprint m² still needed to reach the minimum FCR target."""
    fcr_min_m2, _ = floor_coverage_ratio_bounds(room_area_m2(room))
    return max(0.0, fcr_min_m2 - draft_floor_coverage_m2(draft, room))


def coverage_headroom_m2(draft: RoomLayoutDraft, room: RoomSpec) -> float:
    """Remaining m² of footprint allowed before exceeding the maximum FCR."""
    _, fcr_max_m2 = floor_coverage_ratio_bounds(room_area_m2(room))
    return max(0.0, fcr_max_m2 - draft_floor_coverage_m2(draft, room))


def fcr_summary(draft: RoomLayoutDraft, room: RoomSpec) -> dict[str, float]:
    area = room_area_m2(room)
    footprint = draft_floor_coverage_m2(draft, room)
    fcr_min_m2, fcr_max_m2 = floor_coverage_ratio_bounds(area)
    ratio = footprint / area if area > 0 else 0.0
    return {
        "room_area_m2": area,
        "footprint_m2": footprint,
        "ratio": ratio,
        "min_ratio": FCR_MIN,
        "max_ratio": FCR_MAX,
        "min_m2": fcr_min_m2,
        "max_m2": fcr_max_m2,
        "deficit_m2": max(0.0, fcr_min_m2 - footprint),
        "headroom_m2": max(0.0, fcr_max_m2 - footprint),
    }
