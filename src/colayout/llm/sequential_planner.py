"""Sequential LLM layout planner: anchors first, then expand each zone."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from colayout.catalog.kenney_index import role_for_model
from colayout.catalog.resolve_model import intent_from_model_id
from colayout.llm.anchor_structure import (
    ANCHOR_CHILD_HINTS,
    anchor_count_for_room,
    resolve_anchor_placements,
)
from colayout.llm.draft_from_llm import placement_draft_from_llm_row
from colayout.llm.placement_messages import build_placement_user_message, parse_llm_json
from colayout.llm.room_program import density_tier, room_area_m2
from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    validate_layout_draft,
)
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
ANCHORS_PROMPT_PATH = ROOT / "config" / "prompts" / "room_sequential_anchors.txt"
EXPAND_PROMPT_PATH = ROOT / "config" / "prompts" / "room_sequential_expand.txt"


def _anchor_role_label(p: FurniturePlacementDraft) -> str:
    from colayout.catalog.kenney_index import placement_category, role_for_model

    role = role_for_model(p.model_id)
    cat = placement_category(p.model_id)
    if role in ("tv", "tv_stand") or cat in ("tv", "tv_stand"):
        return "tv"
    return role or cat or "anchor"


def _build_anchors_user_message(room: RoomSpec) -> str:
    base = build_placement_user_message(room)
    n = anchor_count_for_room(room)
    tier = density_tier(room_area_m2(room))
    return (
        f"{base}\n---\n"
        f"Step 1 — place {n} zone anchor(s) for {tier} tier.\n"
        "Tag every piece composition_role=anchor, relative_to=null.\n"
        "Suggested anchor ideas are in the guidance above; you choose furniture_role values.\n"
    )


def _build_expand_user_message(
    room: RoomSpec,
    anchor: FurniturePlacementDraft,
    existing: list[FurniturePlacementDraft],
) -> str:
    role = _anchor_role_label(anchor)
    hint = ANCHOR_CHILD_HINTS.get(role, "support and accent pieces for this zone")
    def _row_summary(p: FurniturePlacementDraft) -> dict:
        intent = intent_from_model_id(p.model_id)
        summary = {
            "id": p.id,
            "furniture_role": intent["furniture_role"],
            "composition_role": p.composition_role,
            "relative_to": p.relative_to,
            "zone": p.zone,
        }
        if "surface" in intent:
            summary["surface"] = intent["surface"]
        return summary

    existing_json = json.dumps(
        [_row_summary(p) for p in existing],
        indent=2,
    )
    anchor_intent = intent_from_model_id(anchor.model_id)
    anchor_role_label = anchor_intent.get("furniture_role", role)
    return (
        f"Room: {room.type} {room.width_m}×{room.length_m} m\n"
        f"Target anchor: id={anchor.id}, furniture_role={anchor_role_label}, "
        f"zone={anchor.zone or 'unspecified'}, role≈{role}\n"
        f"Child ideas: {hint}\n"
        f"Already placed:\n{existing_json}\n"
        f"Anchor position: center_x_m={anchor.center_x_m:.2f}, center_z_m={anchor.center_z_m:.2f}\n"
        f"Valid center range: x in [0, {room.width_m}], z in [0, {room.length_m}] "
        "(southwest origin; never negative).\n"
        "Add only new children for this anchor zone. Do not duplicate existing ids.\n"
    )


def _placement_from_llm_row(
    row: dict,
    room: RoomSpec,
    warnings: list[str],
    *,
    defaults: dict | None = None,
    used_model_ids: set[str] | None = None,
    placements_by_id: dict[str, dict] | None = None,
    resolve_errors: list[str] | None = None,
) -> FurniturePlacementDraft:
    used = used_model_ids if used_model_ids is not None else set()
    by_id = placements_by_id if placements_by_id is not None else {}
    errors = resolve_errors if resolve_errors is not None else warnings

    placement = placement_draft_from_llm_row(
        row,
        room,
        used_model_ids=used,
        placements_by_id=by_id,
        errors=errors,
        defaults=defaults,
    )
    if placement is None:
        raise ValidationError.from_exception_data(
            "FurniturePlacementDraft",
            [{"type": "missing", "loc": ("furniture_role",), "msg": "unresolved"}],
        )

    resolved = placement
    by_id[resolved.id] = resolved.model_dump()
    return resolved


def _call_json(client, model: str, system: str, user: str) -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    return parse_llm_json(raw)


def _merge_placements(
    anchors: list[FurniturePlacementDraft],
    children: list[FurniturePlacementDraft],
) -> list[FurniturePlacementDraft]:
    by_id = {p.id: p for p in anchors}
    merged = list(anchors)
    for p in children:
        if p.id in by_id:
            continue
        merged.append(p)
        by_id[p.id] = p
    ordered = sorted(merged, key=lambda x: x.placement_order)
    return [p.model_copy(update={"placement_order": i}) for i, p in enumerate(ordered, start=1)]


def generate_layout_draft_sequential(
    room: RoomSpec,
    client,
    model: str,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Place anchors, expand each zone, validate."""
    warnings: list[str] = []
    anchors_system = ANCHORS_PROMPT_PATH.read_text(encoding="utf-8")
    expand_system = EXPAND_PROMPT_PATH.read_text(encoding="utf-8")

    anchor_data = _call_json(
        client,
        model,
        anchors_system,
        _build_anchors_user_message(room),
    )
    raw_anchors = anchor_data.get("placements") or []
    if not raw_anchors:
        raise ValueError("anchors step returned no placements")

    used_model_ids: set[str] = set()
    placements_by_id: dict[str, dict] = {}
    anchors: list[FurniturePlacementDraft] = []
    for i, row in enumerate(raw_anchors, start=1):
        anchors.append(
            _placement_from_llm_row(
                row,
                room,
                warnings,
                defaults={
                    "composition_role": "anchor",
                    "relative_to": None,
                    "placement_order": i,
                },
                used_model_ids=used_model_ids,
                placements_by_id=placements_by_id,
            )
        )

    all_placements = list(anchors)
    resolved = resolve_anchor_placements(all_placements, room)
    if not resolved:
        resolved = anchors

    for anchor in resolved:
        try:
            child_data = _call_json(
                client,
                model,
                expand_system,
                _build_expand_user_message(room, anchor, all_placements),
            )
            new_rows = child_data.get("placements") or []
            children: list[FurniturePlacementDraft] = []
            for row in new_rows:
                row = dict(row)
                if row.get("composition_role") == "anchor":
                    row["composition_role"] = "support"
                try:
                    children.append(
                        _placement_from_llm_row(
                            row,
                            room,
                            warnings,
                            used_model_ids=used_model_ids,
                            placements_by_id=placements_by_id,
                        )
                    )
                except ValidationError as row_err:
                    rid = row.get("id", "?")
                    warnings.append(
                        f"(warning) skipped invalid child '{rid}' for zone {anchor.id}: {row_err}"
                    )
            if children:
                all_placements = _merge_placements(all_placements, children)
        except (ValidationError, json.JSONDecodeError) as e:
            warnings.append(f"(warning) expand zone {anchor.id} failed: {e}")
            logger.warning("Expand zone %s failed: %s", anchor.id, e)

    draft = RoomLayoutDraft(
        room_id=room.id,
        room_type=room.type,
        placements=all_placements,
    )
    sanitized, val_errors = validate_layout_draft(draft, room)
    blocking = [e for e in val_errors if is_blocking_placement_error(e)]
    if blocking:
        raise ValueError("; ".join(blocking))
    warnings.extend(val_errors)
    return sanitized, warnings
