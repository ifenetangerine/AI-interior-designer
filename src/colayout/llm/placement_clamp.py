"""Clamp LLM placement centers into room bounds."""

from __future__ import annotations

from colayout.catalog.kenney_index import footprint_for_model
from colayout.schemas.floor import RoomSpec


def clamp_row_centers(
    row: dict,
    room: RoomSpec,
    warnings: list[str],
) -> dict:
    """Clamp centers so footprint fits inside the room (ge=0 safe)."""
    row = dict(row)
    model_id = str(row.get("model_id") or "")
    orient = int(row.get("orientation", 0))
    if orient not in (0, 1, 2, 3):
        orient = 0
        row["orientation"] = orient
    w, d = footprint_for_model(model_id) if model_id else (1.0, 1.0)
    if orient in (1, 3):
        w, d = d, w
    try:
        cx = float(row.get("center_x_m", room.width_m / 2))
        cz = float(row.get("center_z_m", room.length_m / 2))
    except (TypeError, ValueError):
        cx, cz = room.width_m / 2, room.length_m / 2
    orig_cx, orig_cz = cx, cz
    min_x, max_x = w / 2, room.width_m - w / 2
    min_z, max_z = d / 2, room.length_m - d / 2
    cx = max(min_x, min(cx, max_x)) if max_x >= min_x else room.width_m / 2
    cz = max(min_z, min(cz, max_z)) if max_z >= min_z else room.length_m / 2
    row["center_x_m"] = round(cx, 3)
    row["center_z_m"] = round(cz, 3)
    if abs(orig_cx - cx) > 0.01 or abs(orig_cz - cz) > 0.01:
        label = row.get("id", "?")
        warnings.append(
            f"(info) clamped LLM center for '{label}' "
            f"from ({orig_cx:.2f}, {orig_cz:.2f}) to ({cx:.2f}, {cz:.2f})"
        )
    return row
