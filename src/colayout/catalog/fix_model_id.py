"""Map invalid LLM model_id strings to the closest Kenney catalog id."""

from __future__ import annotations

import difflib
import re

from colayout.catalog.kenney_index import catalog_for_room, is_allowed_in_room, load_catalog

# Common LLM aliases → catalog id (checked before fuzzy match).
_ALIASES: dict[str, str] = {
    "tablelamp": "lampSquareTable",
    "floorlamp": "lampSquareFloor",
    "plantpot": "pottedPlant",
    "armchair": "loungeChair",
    "chairarmchair": "loungeChair",
    "drawertable": "sideTableDrawers",
    "sidetable": "sideTable",
    "coffeetable": "tableCoffee",
    "tvstand": "cabinetTelevision",
    "bookshelf": "bookcaseClosed",
    "wardrobe": "cabinetBed",
    "nightstand": "sideTable",
}


def _catalog_ids(room_type: str, catalog: dict | None = None) -> list[str]:
    return [row["id"] for row in catalog_for_room(room_type, catalog)]


def _normalize_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def closest_catalog_id(
    raw: str,
    room_type: str,
    *,
    catalog: dict | None = None,
) -> str | None:
    """Deterministic best match for an invalid model_id (None if catalog empty)."""
    if not raw:
        return None
    ids = _catalog_ids(room_type, catalog)
    if not ids:
        return None
    if is_allowed_in_room(raw, room_type):
        return raw

    alias = _ALIASES.get(_normalize_key(raw))
    if alias and alias in ids:
        return alias

    lower_to_id = {mid.lower(): mid for mid in ids}
    if raw.lower() in lower_to_id:
        return lower_to_id[raw.lower()]

    raw_norm = _normalize_key(raw)
    if raw_norm in _ALIASES and _ALIASES[raw_norm] in ids:
        return _ALIASES[raw_norm]

    scored: list[tuple[float, str]] = []
    for mid in ids:
        mid_norm = _normalize_key(mid)
        ratio = difflib.SequenceMatcher(None, raw_norm, mid_norm).ratio()
        if raw_norm in mid_norm or mid_norm in raw_norm:
            ratio += 0.25
        scored.append((ratio, mid))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def fix_model_id(
    raw: str,
    room_type: str,
    *,
    catalog: dict | None = None,
) -> tuple[str | None, bool]:
    """Return (fixed_id, was_changed)."""
    cat = catalog or load_catalog()
    if is_allowed_in_room(raw, room_type):
        return raw, False
    fixed = closest_catalog_id(raw, room_type, catalog=cat)
    if fixed is None:
        return None, False
    return fixed, fixed != raw
