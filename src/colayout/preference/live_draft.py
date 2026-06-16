"""Live LLM layout drafts for preference training (no disk cache)."""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from colayout.llm.few_shot import few_shot_golden_ids
from colayout.llm.provider import LLMProvider, get_llm_provider
from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    validate_layout_draft,
)
from colayout.schemas.architecture import default_architecture
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft

logger = logging.getLogger(__name__)

PICKS_PER_DESIGN = 7
PREFERENCE_ROOM_TYPES = ("bedroom", "living_room", "kitchen")
# (min_w, min_l), (max_w, max_l) in metres
ROOM_SIZE_RANGES: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "bedroom": ((3.2, 2.8), (5.5, 4.5)),
    "living_room": ((3.5, 3.0), (6.5, 5.5)),
    "kitchen": ((4.0, 3.5), (6.0, 5.0)),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_design_id(room_type: str) -> str:
    return f"live_{room_type}_{uuid.uuid4().hex[:8]}"


def random_room_spec(
    room_type: str,
    design_id: str,
    rng: random.Random,
) -> RoomSpec:
    (wmin, lmin), (wmax, lmax) = ROOM_SIZE_RANGES[room_type]
    width_m = round(rng.uniform(wmin, wmax), 1)
    length_m = round(rng.uniform(lmin, lmax), 1)
    arch = default_architecture(room_type, width_m, length_m)
    return RoomSpec(
        id=design_id,
        type=room_type,
        width_m=width_m,
        length_m=length_m,
        architecture=arch,
    )


def room_from_session(record: dict[str, Any]) -> RoomSpec:
    from colayout.schemas.architecture import RoomArchitecture

    arch = record.get("architecture")
    return RoomSpec(
        id=record.get("design_id", "design"),
        type=record["room_type"],
        width_m=float(record["width_m"]),
        length_m=float(record["length_m"]),
        architecture=RoomArchitecture.model_validate(arch) if arch else None,
    )


def draft_from_session(session: dict[str, Any]) -> RoomLayoutDraft:
    draft = session["draft"]
    return RoomLayoutDraft.model_validate(
        {
            **draft,
            "room_id": draft.get("room_id") or session["design_id"],
            "room_type": draft.get("room_type") or session["room_type"],
        }
    )


def generate_live_draft(
    room_type: str,
    llm: LLMProvider | None = None,
    *,
    use_mock: bool = False,
    max_attempts: int = 3,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Random room + LLM layout draft for a new preference session."""
    provider = llm or get_llm_provider(use_mock=use_mock)
    rng = rng or random.Random()
    few_shot_ids = few_shot_golden_ids(room_type)
    last_warnings: list[str] = []

    for attempt in range(max_attempts):
        design_id = new_design_id(room_type)
        room = random_room_spec(room_type, design_id, rng)
        draft = provider.generate_layout_draft(room)
        draft, val_errors = validate_layout_draft(draft, room)
        warnings = list(getattr(provider, "last_generation_warnings", None) or [])
        warnings.extend(val_errors)
        last_warnings = warnings
        blocking = [e for e in val_errors if is_blocking_placement_error(e)]
        if not blocking:
            return {
                "design_id": design_id,
                "room_type": room_type,
                "width_m": room.width_m,
                "length_m": room.length_m,
                "architecture": (
                    room.architecture.model_dump() if room.architecture else None
                ),
                "draft": draft.model_dump(),
                "few_shot_ids": few_shot_ids,
                "mock_llm": use_mock or provider.__class__.__name__ == "MockLLMProvider",
                "warnings": warnings,
                "generated_at": _now_iso(),
                "picks_on_design": 0,
            }
        logger.warning(
            "Live draft attempt %d/%d for %s had blocking errors: %s",
            attempt + 1,
            max_attempts,
            room_type,
            blocking[:3],
        )

    raise RuntimeError(
        f"Failed to generate valid live draft for {room_type} "
        f"after {max_attempts} attempts: {last_warnings[:5]}"
    )


def session_needs_rotation(session: dict[str, Any] | None) -> bool:
    if session is None:
        return True
    return int(session.get("picks_on_design", 0)) >= PICKS_PER_DESIGN


def picks_until_rotation(session: dict[str, Any] | None) -> int:
    if session is None:
        return PICKS_PER_DESIGN
    return max(0, PICKS_PER_DESIGN - int(session.get("picks_on_design", 0)))
