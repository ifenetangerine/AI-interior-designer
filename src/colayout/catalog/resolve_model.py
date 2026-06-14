"""Resolve LLM furniture_role + intent to a concrete Kenney model_id."""

from __future__ import annotations

import hashlib
import re

from colayout.catalog.kenney_index import (
    SURFACE_KIND_BY_MODEL,
    asset_by_id,
    catalog_for_room,
    is_allowed_in_room,
    load_catalog,
    placement_category,
    role_for_model,
)

COUNTER_SEGMENT_ROLES = frozenset({"counter_end", "counter_bar", "counter_base"})

# LLM-friendly aliases → canonical catalog role or virtual role key.
ROLE_ALIASES: dict[str, str] = {
    "accent_chair": "chair",
    "armchair": "chair",
    "dining_chair": "chair",
    "reading_chair": "chair",
    "lounge_chair": "chair",
    "barstool": "bar_stool",
    "stool": "bar_stool",
    "stovetop": "stove",
    "oven": "stove",
    "counter": "counter_segment",
    "counter_base": "counter_segment",
    "counter_bar": "counter_segment",
    "counter_end": "counter_segment",
    "night_stand": "nightstand",
    "coffee_table": "coffee_table",
    "dining_table": "dining_table",
    "tv_screen": "tv",
    "television": "tv",
    "bookshelf": "bookshelf",
    "wardrobe": "wardrobe",
    "dresser": "dresser",
    "plant": "plant",
    "rug": "rug",
    "lamp": "lamp",
    "decor": "decor",
    "fridge": "fridge",
    "refrigerator": "fridge",
    "sink": "sink",
    "sofa": "sofa",
    "couch": "sofa",
    "bed": "bed",
    "desk": "desk",
    "chair": "chair",
}

VIRTUAL_ROLES = frozenset(
    {"tv_console", "counter_segment", "side_table", "storage_cabinet"}
)


def normalize_furniture_role(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"[\s-]+", "_", str(raw).strip().lower())
    return ROLE_ALIASES.get(key, key)


def _stable_index(key: str, size: int) -> int:
    if size <= 0:
        return 0
    digest = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
    return int(digest, 16) % size


def _pick_model_id(
    candidates: list[str],
    *,
    placement_id: str,
    used_model_ids: set[str],
) -> str | None:
    if not candidates:
        return None
    ordered = sorted(candidates)
    unused = [mid for mid in ordered if mid not in used_model_ids]
    pool = unused if unused else ordered
    return pool[_stable_index(placement_id, len(pool))]


def _catalog_assets(room_type: str, catalog: dict | None = None) -> list[dict]:
    cat = catalog or load_catalog()
    allowed = {row["id"] for row in catalog_for_room(room_type, cat)}
    return [a for a in cat.get("assets", []) if a.get("id") in allowed]


def _candidates_for_role(
    role: str,
    room_type: str,
    *,
    surface: str | None = None,
    catalog: dict | None = None,
) -> list[str]:
    cat = catalog or load_catalog()
    assets = _catalog_assets(room_type, cat)

    if role == "counter_segment":
        return sorted(
            {
                a["id"]
                for a in assets
                if a.get("role") in COUNTER_SEGMENT_ROLES
            }
        )

    if role == "tv_console":
        default = cat.get("category_defaults", {}).get("tv_console")
        ids = {
            a["id"]
            for a in assets
            if a.get("role") == "nightstand"
            or a.get("category") in ("side_table", "nightstand")
        }
        if default and default in ids:
            return [default, *sorted(mid for mid in ids if mid != default)]
        return sorted(ids)

    if role == "side_table":
        return sorted(
            {
                a["id"]
                for a in assets
                if a.get("category") in ("side_table", "nightstand")
                or a.get("role") == "nightstand"
            }
        )

    if role == "storage_cabinet":
        return sorted(
            {a["id"] for a in assets if a.get("role") == "storage_cabinet"}
        )

    ids = sorted({a["id"] for a in assets if a.get("role") == role})
    if role == "lamp" and surface:
        surf = surface.strip().lower()
        filtered = [
            mid
            for mid in ids
            if SURFACE_KIND_BY_MODEL.get(mid, "floor") == surf
        ]
        if filtered:
            return sorted(filtered)
    return ids


def infer_lamp_surface(
    row: dict,
    *,
    placements_by_id: dict[str, dict] | None = None,
) -> str | None:
    explicit = row.get("surface")
    if explicit:
        return str(explicit).strip().lower()
    on_surface = row.get("on_surface_of")
    if on_surface:
        return "table"
    if placements_by_id and row.get("relative_to"):
        parent = placements_by_id.get(str(row["relative_to"]))
        if parent:
            parent_role = normalize_furniture_role(
                parent.get("furniture_role")
            ) or (
                role_for_model(parent["model_id"])
                if parent.get("model_id")
                else None
            )
            if parent_role in ("desk", "nightstand", "side_table", "tv_console"):
                return "table"
    note = str(row.get("note") or "").lower()
    if "table lamp" in note or "on nightstand" in note or "on desk" in note:
        return "table"
    if "floor lamp" in note:
        return "floor"
    if "wall" in note:
        return "wall"
    return "floor"


def resolve_model_from_intent(
    *,
    placement_id: str,
    furniture_role: str,
    room_type: str,
    surface: str | None = None,
    used_model_ids: set[str] | None = None,
    catalog: dict | None = None,
) -> str | None:
    """Pick a catalog model_id for a furniture_role (+ optional lamp surface)."""
    role = normalize_furniture_role(furniture_role)
    if not role:
        return None

    used = used_model_ids or set()
    cat = catalog or load_catalog()

    if role not in VIRTUAL_ROLES and role not in {
        a.get("role") for a in _catalog_assets(room_type, cat)
    }:
        default = cat.get("category_defaults", {}).get(role)
        if default and is_allowed_in_room(default, room_type):
            return default

    candidates = _candidates_for_role(
        role, room_type, surface=surface, catalog=cat
    )
    default = cat.get("category_defaults", {}).get(role)
    if not candidates:
        if default and is_allowed_in_room(default, room_type):
            return default
        return None

    if default and default in candidates and role in ("tv_console", "storage_cabinet"):
        return default

    return _pick_model_id(
        candidates,
        placement_id=placement_id,
        used_model_ids=used,
    )


def intent_from_model_id(model_id: str, catalog: dict | None = None) -> dict[str, str]:
    """Derive furniture_role (+ surface for lamps) from a resolved model_id."""
    role = role_for_model(model_id, catalog)
    cat = catalog or load_catalog()
    defaults = cat.get("category_defaults", {})

    furniture_role = role
    for key, default_id in defaults.items():
        if default_id == model_id and key in VIRTUAL_ROLES:
            furniture_role = key
            break

    if role == "nightstand" and model_id == defaults.get("tv_console"):
        furniture_role = "tv_console"

    out: dict[str, str] = {"furniture_role": furniture_role}
    if role == "lamp":
        out["surface"] = SURFACE_KIND_BY_MODEL.get(model_id, "floor")
    return out


def catalog_roles_prompt_json(room_type: str, catalog: dict | None = None) -> str:
    """Compact role list for LLM prompts (no raw model_id strings)."""
    import json as _json

    cat = catalog or load_catalog()
    assets = _catalog_assets(room_type, cat)
    roles = sorted({a.get("role", "decor") for a in assets if a.get("role")})
    roles.extend(r for r in sorted(VIRTUAL_ROLES) if r not in roles)

    grouped: dict[str, list[str]] = {}
    for role in roles:
        if role == "lamp":
            grouped[role] = ["table", "floor", "wall"]
            continue
        if role == "counter_segment":
            grouped[role] = ["any counter module (end, bar, base)"]
            continue
        grouped[role] = ["pick this role; exact model chosen by the system"]

    payload = {
        "furniture_roles": grouped,
        "output_fields": {
            "furniture_role": "required — one role from furniture_roles",
            "surface": "required when furniture_role is lamp (table|floor|wall)",
            "model_id": "omit — never output model_id",
        },
        "virtual_roles": {
            "tv_console": "low TV stand / side table under the TV screen",
            "side_table": "sofa-arm side table (not the TV console)",
            "counter_segment": "kitchen counter module in a run",
            "storage_cabinet": "closed storage on a wall",
        },
    }
    return _json.dumps(payload, indent=2)
