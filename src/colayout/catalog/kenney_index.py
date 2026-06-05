"""Kenney catalog index: roles, room filters, footprints for LLM and validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data" / "catalog" / "kenney_catalog.json"

# Roles that participate in kitchen counter runs (ordered for chain assembly)
COUNTER_RUN_ROLES = (
    "counter_end",
    "counter_bar",
    "counter_base",
    "stove",
    "sink",
)

CHAIN_ORDER = {
    "counter_end": 0,
    "counter_bar": 1,
    "counter_base": 2,
    "stove": 3,
    "sink": 4,
}

ANCHOR_ROLE_BY_ROOM: dict[str, str] = {
    "bedroom": "bed",
    "living_room": "sofa",
    "kitchen": "dining_table",
    "dining": "dining_table",
}

STACKABLE_CHILD_ROLES = frozenset({"lamp", "plant", "rug", "decor"})

SURFACE_KIND_BY_MODEL: dict[str, str] = {
    "lampRoundFloor": "floor",
    "lampSquareFloor": "floor",
    "lampWall": "wall",
    "lampSquareCeiling": "wall",
    "lampSquareTable": "table",
    "lampRoundTable": "table",
}

STORAGE_ROLES = frozenset(
    {
        "wardrobe",
        "dresser",
        "fridge",
        "counter_base",
        "counter_bar",
        "counter_end",
        "stove",
        "sink",
        "tv_stand",
        "bookshelf",
    }
)


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    if not CATALOG_PATH.is_file():
        raise FileNotFoundError(f"Kenney catalog not found: {CATALOG_PATH}")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _assets(catalog: dict | None = None) -> list[dict]:
    return (catalog or load_catalog()).get("assets", [])


def asset_by_id(model_id: str, catalog: dict | None = None) -> dict | None:
    for a in _assets(catalog):
        if a["id"] == model_id:
            return a
    return None


def role_for_model(model_id: str, catalog: dict | None = None) -> str:
    a = asset_by_id(model_id, catalog)
    return a.get("role", "decor") if a else "decor"


def placement_category(model_id: str, catalog: dict | None = None) -> str:
    a = asset_by_id(model_id, catalog)
    if a:
        return a.get("category", "misc")
    return "misc"


def footprint_for_model(
    model_id: str, catalog: dict | None = None
) -> tuple[float, float]:
    a = asset_by_id(model_id, catalog)
    if not a:
        return 1.0, 1.0
    return float(a["width_m"]), float(a["depth_m"])


def height_for_model(model_id: str, catalog: dict | None = None) -> float:
    a = asset_by_id(model_id, catalog)
    if not a:
        return 0.5
    return float(a.get("height_m", 0.5))


def surface_kind_for_model(model_id: str, catalog: dict | None = None) -> str:
    a = asset_by_id(model_id, catalog)
    if a and a.get("surface"):
        return str(a["surface"])
    if model_id in SURFACE_KIND_BY_MODEL:
        return SURFACE_KIND_BY_MODEL[model_id]
    mid = model_id.lower()
    if "floor" in mid or "roundfloor" in mid:
        return "floor"
    if "wall" in mid or "ceiling" in mid:
        return "wall"
    role = role_for_model(model_id, catalog)
    if role == "lamp":
        return "table"
    if role == "rug":
        return "floor"
    return "floor"


def is_stackable_child_role(role: str) -> bool:
    return role in STACKABLE_CHILD_ROLES


def is_allowed_in_room(
    model_id: str, room_type: str, catalog: dict | None = None
) -> bool:
    a = asset_by_id(model_id, catalog)
    if not a:
        return False
    rooms = a.get("rooms") or []
    return room_type in rooms


def catalog_for_room(room_type: str, catalog: dict | None = None) -> list[dict]:
    """Compact rows for LLM prompt: placeable models for this room type."""
    cat = catalog or load_catalog()
    rows: list[dict] = []
    for a in cat.get("assets", []):
        rooms = a.get("rooms") or []
        if room_type not in rooms:
            continue
        role = a.get("role", "decor")
        if role == "excluded":
            continue
        rows.append(
            {
                "id": a["id"],
                "role": role,
                "category": a.get("category", "misc"),
                "width_m": a["width_m"],
                "depth_m": a["depth_m"],
            }
        )
    return rows


PROMPT_ROLE_GROUPS: dict[str, list[str]] = {
    "Functional": (
        "bed",
        "chair",
        "desk",
        "sofa",
        "dining_table",
        "coffee_table",
        "counter_end",
        "counter_bar",
        "counter_base",
        "stove",
        "sink",
        "fridge",
        "bar_stool",
    ),
    "Storage": ("wardrobe", "dresser", "tv_stand", "bookshelf"),
    "Lighting": ("lamp",),
    "Plants_and_decor": ("plant", "rug", "decor"),
}

PROMPT_EXCLUDED_ROLES = frozenset(
    {
        "counter_upper",
    }
)


def catalog_prompt_json(room_type: str, catalog: dict | None = None) -> str:
    import json as _json

    rows = catalog_for_room(room_type, catalog)
    grouped: dict[str, list[dict]] = {k: [] for k in PROMPT_ROLE_GROUPS}
    grouped["Other"] = []
    for row in rows:
        role = row.get("role", "decor")
        if role in PROMPT_EXCLUDED_ROLES:
            continue
        placed = False
        for group, roles in PROMPT_ROLE_GROUPS.items():
            if role in roles:
                grouped[group].append(row)
                placed = True
                break
        if not placed:
            grouped["Other"].append(row)
    return _json.dumps({k: v for k, v in grouped.items() if v}, indent=2)


def resolve_model_id(
    item_model_id: str | None,
    item_category: str | None,
    catalog: dict | None = None,
) -> str | None:
    """Resolve model_id from explicit id or legacy category_defaults."""
    if item_model_id:
        return item_model_id
    if not item_category:
        return None
    cat = catalog or load_catalog()
    defaults = cat.get("category_defaults", {})
    return defaults.get(item_category)


def normalize_furniture_item(
    item_id: str,
    model_id: str | None,
    category: str | None,
    width_m: float | None,
    length_m: float | None,
    catalog: dict | None = None,
) -> tuple[dict | None, str | None]:
    """Return normalized fields or error message."""
    cat = catalog or load_catalog()
    mid = resolve_model_id(model_id, category, cat)
    if not mid:
        return None, f"furniture '{item_id}' missing model_id and unknown category"
    asset = asset_by_id(mid, cat)
    if not asset:
        return None, f"unknown model_id '{mid}' for '{item_id}'"
    w, d = footprint_for_model(mid, cat)
    return {
        "id": item_id,
        "model_id": mid,
        "category": asset.get("category", "misc"),
        "role": asset.get("role", "decor"),
        "width_m": w,
        "length_m": d,
    }, None
