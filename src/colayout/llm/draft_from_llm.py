"""Convert LLM placement JSON (furniture_role intent) into RoomLayoutDraft."""

from __future__ import annotations

from colayout.catalog.resolve_model import (
    infer_lamp_surface,
    intent_from_model_id,
    normalize_furniture_role,
    resolve_model_from_intent,
)
from colayout.catalog.kenney_index import is_allowed_in_room, role_for_model
from colayout.llm.placement_clamp import clamp_row_centers
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


def _resolve_row_model_id(
    row: dict,
    room: RoomSpec,
    *,
    used_model_ids: set[str],
    placements_by_id: dict[str, dict],
    errors: list[str],
) -> str | None:
    placement_id = str(row.get("id") or "")
    raw_role = row.get("furniture_role") or row.get("role")
    furniture_role = normalize_furniture_role(str(raw_role)) if raw_role else None

    legacy_model_id = row.get("model_id")
    if legacy_model_id and is_allowed_in_room(str(legacy_model_id), room.type):
        if not furniture_role:
            return str(legacy_model_id)
        errors.append(
            f"(info) ignored LLM model_id '{legacy_model_id}' for '{placement_id}' "
            f"— resolved from furniture_role '{furniture_role}'"
        )

    if not furniture_role:
        if legacy_model_id:
            errors.append(
                f"unknown model_id '{legacy_model_id}' for '{placement_id}' — removed"
            )
        else:
            errors.append(f"missing furniture_role for '{placement_id}' — removed")
        return None

    surface = None
    if furniture_role == "lamp":
        surface = infer_lamp_surface(row, placements_by_id=placements_by_id)

    model_id = resolve_model_from_intent(
        placement_id=placement_id,
        furniture_role=furniture_role,
        room_type=room.type,
        surface=surface,
        used_model_ids=used_model_ids,
    )
    if not model_id:
        errors.append(
            f"no catalog match for furniture_role '{furniture_role}' "
            f"on '{placement_id}' — removed"
        )
        return None

    used_model_ids.add(model_id)
    return model_id


def resolve_llm_placement_rows(
    rows: list[dict],
    room: RoomSpec,
) -> tuple[list[dict], list[str]]:
    """Attach model_id to each LLM row from furniture_role intent."""
    errors: list[str] = []
    used_model_ids: set[str] = set()
    placements_by_id = {str(r.get("id")): dict(r) for r in rows if r.get("id")}

    resolved: list[dict] = []
    for row in rows:
        row = dict(row)
        row.pop("model_id", None)
        row.pop("role", None)

        model_id = _resolve_row_model_id(
            row,
            room,
            used_model_ids=used_model_ids,
            placements_by_id=placements_by_id,
            errors=errors,
        )
        if not model_id:
            continue

        row["model_id"] = model_id
        row.pop("furniture_role", None)
        row.pop("surface", None)
        resolved.append(row)
        placements_by_id[str(row["id"])] = row

    return resolved, errors


def room_layout_draft_from_llm_data(
    data: dict,
    room: RoomSpec,
) -> tuple[RoomLayoutDraft, list[str]]:
    """Parse LLM JSON dict into a RoomLayoutDraft with resolved model_ids."""
    payload = dict(data)
    raw_rows = payload.get("placements") or []
    resolved_rows, errors = resolve_llm_placement_rows(raw_rows, room)
    clamped: list[dict] = []
    for row in resolved_rows:
        clamped.append(clamp_row_centers(row, room, errors))
    payload["placements"] = clamped
    draft = RoomLayoutDraft.model_validate(payload)
    return draft, errors


def placement_draft_from_llm_row(
    row: dict,
    room: RoomSpec,
    *,
    used_model_ids: set[str],
    placements_by_id: dict[str, dict],
    errors: list[str],
    defaults: dict | None = None,
) -> FurniturePlacementDraft | None:
    """Resolve one LLM row to FurniturePlacementDraft."""
    row = dict(row)
    if defaults:
        for key, val in defaults.items():
            row.setdefault(key, val)

    model_id = _resolve_row_model_id(
        row,
        room,
        used_model_ids=used_model_ids,
        placements_by_id=placements_by_id,
        errors=errors,
    )
    if not model_id:
        return None

    row["model_id"] = model_id
    row.pop("furniture_role", None)
    row.pop("surface", None)
    row.pop("role", None)
    row = clamp_row_centers(row, room, errors)
    return FurniturePlacementDraft.model_validate(row)


def placement_row_for_prompt(p: dict) -> dict:
    """Few-shot / debug: show furniture_role instead of model_id."""
    out = dict(p)
    model_id = out.pop("model_id", None)
    if model_id and "furniture_role" not in out:
        intent = intent_from_model_id(str(model_id))
        out.update(intent)
    elif model_id:
        role = role_for_model(str(model_id))
        if role == "lamp" and "surface" not in out:
            out.setdefault("surface", infer_lamp_surface(out))
    out.pop("model_id", None)
    return out
