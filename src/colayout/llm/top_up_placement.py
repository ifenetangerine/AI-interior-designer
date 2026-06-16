"""Merge floor-coverage top-up additions into an existing layout draft."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, ValidationError

from colayout.llm.floor_coverage import is_draft_underfurnished
from colayout.llm.top_up_messages import build_top_up_user_message
from colayout.llm.validate_placement import validate_layout_draft
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

logger = logging.getLogger(__name__)


class TopUpResponse(BaseModel):
    additions: list[FurniturePlacementDraft] = Field(default_factory=list)


def merge_top_up_additions(
    draft: RoomLayoutDraft,
    additions: list[FurniturePlacementDraft],
) -> RoomLayoutDraft:
    """Append new placements; skip ids that already exist."""
    if not additions:
        return draft
    existing_ids = {p.id for p in draft.placements}
    merged = list(draft.placements)
    next_order = max((p.placement_order for p in merged), default=0) + 1
    for item in additions:
        if item.id in existing_ids:
            logger.warning("Top-up skipped duplicate id '%s'", item.id)
            continue
        merged.append(
            item.model_copy(update={"placement_order": next_order})
        )
        existing_ids.add(item.id)
        next_order += 1
    return draft.model_copy(update={"placements": merged})


def apply_top_up_response(
    room: RoomSpec,
    draft: RoomLayoutDraft,
    raw: str,
    *,
    parse_json,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Parse top-up JSON, merge additions, and re-sanitize."""
    messages: list[str] = []
    try:
        data = parse_json(raw)
        response = TopUpResponse.model_validate(data)
    except (ValidationError, ValueError, TypeError) as e:
        messages.append(f"(warning) top-up parse failed: {e}")
        return draft, messages

    if not response.additions:
        messages.append("(info) top-up LLM returned no additions")
        return draft, messages

    merged = merge_top_up_additions(draft, response.additions)
    sanitized, val_msgs = validate_layout_draft(merged, room)
    messages.extend(val_msgs)
    messages.append(
        f"(info) top-up added {len(response.additions)} piece(s); "
        f"total placements now {len(sanitized.placements)}"
    )
    return sanitized, messages


def maybe_top_up_layout_draft(
    room: RoomSpec,
    draft: RoomLayoutDraft,
    *,
    llm_complete,
    system_prompt: str,
    parse_json,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Run a second LLM pass when floor coverage is below 35%."""
    messages: list[str] = []
    if not is_draft_underfurnished(draft, room):
        return draft, messages

    logger.info(
        "Room %s under-furnished (FCR below %.0f%%); running top-up LLM pass",
        room.id,
        35,
    )
    user_content = build_top_up_user_message(room, draft)
    try:
        raw = llm_complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except Exception as e:
        logger.warning("Room %s top-up LLM failed: %s", room.id, e)
        messages.append(f"(warning) top-up LLM failed: {e}")
        return draft, messages

    updated, top_msgs = apply_top_up_response(
        room, draft, raw, parse_json=parse_json
    )
    messages.extend(top_msgs)
    if is_draft_underfurnished(updated, room):
        messages.append(
            "(warning) floor coverage still below 35% after top-up pass"
        )
    return updated, messages
