"""Category-based placement rules: stacking and pairwise distance bounds."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config" / "placement" / "category_constraints.yaml"
LEARNED_CONFIG_PATH = ROOT / "config" / "placement" / "category_constraints.learned.yaml"

ThetaOverrides = dict[str, float] | None

StackMode = Literal["on_top", "beneath"]

PLACEMENT_CATEGORIES: tuple[str, ...] = (
    "bed",
    "chair",
    "desk",
    "sofa",
    "wardrobe",
    "tv",
    "coffee_table",
    "counter",
    "fridge",
    "dining_table",
    "nightstand",
    "bookshelf",
    "dresser",
    "decor",
    "rug",
    "lamp_desk",
    "lamp_floor",
)

DEFAULT_STACKING = {"on_top": False, "beneath": False}


@lru_cache(maxsize=1)
def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Category constraints not found: {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def stacking_rules(category: str) -> dict[str, bool]:
    cfg = load_config()
    stacking = cfg.get("stacking") or {}
    rules = stacking.get(category) or stacking.get("default") or DEFAULT_STACKING
    return {
        "on_top": bool(rules.get("on_top", False)),
        "beneath": bool(rules.get("beneath", False)),
    }


def stack_parent_categories(mode: StackMode) -> frozenset[str]:
    cfg = load_config()
    parents = (cfg.get("stack_parents") or {}).get(mode) or []
    return frozenset(str(p) for p in parents)


def valid_stack_parent(child_cat: str, parent_cat: str, mode: StackMode) -> bool:
    rules = stacking_rules(child_cat)
    if mode == "on_top" and not rules["on_top"]:
        return False
    if mode == "beneath" and not rules["beneath"]:
        return False
    return parent_cat in stack_parent_categories(mode)


def is_stackable_category(category: str) -> bool:
    rules = stacking_rules(category)
    return rules["on_top"] or rules["beneath"]


def _pair_key(cat_a: str, cat_b: str) -> tuple[str, str]:
    return tuple(sorted((cat_a, cat_b)))  # type: ignore[return-value]


def _lookup_pair_bounds(cat_a: str, cat_b: str) -> tuple[str, str, dict] | None:
    cfg = load_config()
    pairs = (cfg.get("distance_m") or {}).get("pairs") or {}
    if cat_a in pairs and cat_b in pairs[cat_a]:
        return cat_a, cat_b, pairs[cat_a][cat_b]
    if cat_b in pairs and cat_a in pairs[cat_b]:
        return cat_b, cat_a, pairs[cat_b][cat_a]
    return None


def has_explicit_pair_bounds(cat_a: str, cat_b: str) -> bool:
    """True when YAML defines an explicit min/max band for this category pair."""
    return _lookup_pair_bounds(cat_a, cat_b) is not None


def pair_theta_key(cat_a: str, cat_b: str, field: Literal["min_m", "max_m"]) -> str:
    return f"pair.{cat_a}.{cat_b}.{field}"


def wall_theta_key(category: str, field: Literal["min_m", "max_m"]) -> str:
    return f"wall.{category}.{field}"


DOOR_CLEARANCE_KEY = "door.clearance_min_m"


def _override_value(overrides: ThetaOverrides, *keys: str) -> float | None:
    if not overrides:
        return None
    for key in keys:
        if key in overrides:
            return float(overrides[key])
    return None


def iter_tunable_pair_specs() -> list[tuple[str, str, float, float]]:
    """Yield (cat_a, cat_b, default_min_m, default_max_m) for explicit YAML pairs."""
    cfg = load_config()
    defaults = (cfg.get("distance_m") or {}).get("defaults") or {}
    default_min = float(defaults.get("min", 0.0))
    seen: set[frozenset[str]] = set()
    specs: list[tuple[str, str, float, float]] = []
    pairs = (cfg.get("distance_m") or {}).get("pairs") or {}
    for cat_a, neighbors in pairs.items():
        for cat_b, bounds in (neighbors or {}).items():
            key = frozenset({cat_a, cat_b})
            if key in seen:
                continue
            seen.add(key)
            min_m = float(bounds.get("min", default_min))
            max_raw = bounds.get("max")
            if max_raw is None:
                continue
            max_m = float(max_raw)
            specs.append((cat_a, cat_b, min_m, max_m))
    return specs


def iter_tunable_wall_specs() -> list[tuple[str, float, float | None]]:
    """Yield (category, default_min_m, default_max_m) for non-exempt wall rules."""
    cfg = load_config()
    section = cfg.get("wall_distance_m") or {}
    defaults = section.get("defaults") or {}
    default_min = float(defaults.get("min", 0.0))
    default_max_raw = defaults.get("max")
    default_max = None if default_max_raw is None else float(default_max_raw)
    specs: list[tuple[str, float, float | None]] = []
    for category, bounds in (section.get("categories") or {}).items():
        if wall_distance_exempt(category):
            continue
        min_m = float(bounds.get("min", default_min))
        max_raw = bounds.get("max")
        max_m = default_max if max_raw is None else float(max_raw)
        specs.append((category, min_m, max_m))
    return specs


def build_learned_config(theta: dict[str, float]) -> dict:
    """Merge base category_constraints with learned θ distance overrides."""
    import copy

    data = copy.deepcopy(load_config())
    for cat_a, cat_b, _min_d, _max_d in iter_tunable_pair_specs():
        pairs = data.setdefault("distance_m", {}).setdefault("pairs", {})
        pairs.setdefault(cat_a, {})
        entry = pairs[cat_a].setdefault(cat_b, {})
        min_key = pair_theta_key(cat_a, cat_b, "min_m")
        max_key = pair_theta_key(cat_a, cat_b, "max_m")
        if min_key in theta:
            entry["min"] = round(float(theta[min_key]), 3)
        if max_key in theta:
            entry["max"] = round(float(theta[max_key]), 3)

    wall_section = data.setdefault("wall_distance_m", {})
    categories = wall_section.setdefault("categories", {})
    for category, _min_d, _max_d in iter_tunable_wall_specs():
        entry = categories.setdefault(category, {})
        min_key = wall_theta_key(category, "min_m")
        max_key = wall_theta_key(category, "max_m")
        if min_key in theta:
            entry["min"] = round(float(theta[min_key]), 3)
        if max_key in theta:
            entry["max"] = round(float(theta[max_key]), 3)

    return data


def distance_bounds_m(
    cat_a: str,
    cat_b: str,
    room_diag_m: float,
    *,
    overrides: ThetaOverrides = None,
) -> tuple[float, float]:
    """Return (min_m, max_m) for centroid L1 distance between two categories."""
    defaults = (load_config().get("distance_m") or {}).get("defaults") or {}
    default_min = float(defaults.get("min", 0.0))
    default_max_raw = defaults.get("max")
    default_max = room_diag_m if default_max_raw is None else float(default_max_raw)

    if cat_a == cat_b:
        return default_min, default_max

    explicit = _lookup_pair_bounds(cat_a, cat_b)
    if explicit:
        key_a, key_b, bounds = explicit
        min_m = float(bounds.get("min", default_min))
        max_raw = bounds.get("max")
        max_m = room_diag_m if max_raw is None else float(max_raw)
        min_override = _override_value(
            overrides,
            pair_theta_key(key_a, key_b, "min_m"),
            pair_theta_key(key_b, key_a, "min_m"),
        )
        max_override = _override_value(
            overrides,
            pair_theta_key(key_a, key_b, "max_m"),
            pair_theta_key(key_b, key_a, "max_m"),
        )
        if min_override is not None:
            min_m = min_override
        if max_override is not None:
            max_m = max_override
        return min_m, max_m

    return default_min, default_max


def distance_bounds_centi(
    cat_a: str,
    cat_b: str,
    room_diag_m: float,
    cell_m: float,
    *,
    overrides: ThetaOverrides = None,
) -> tuple[int, int]:
    min_m, max_m = distance_bounds_m(
        cat_a, cat_b, room_diag_m, overrides=overrides
    )
    return (
        int(round(min_m / cell_m)) * 100,
        int(round(max_m / cell_m)) * 100,
    )


def is_valid_surface_stack(
    child_model_id: str,
    parent_model_id: str,
    *,
    mode: StackMode = "on_top",
) -> bool:
    """Whether child may stack on parent per category rules."""
    from colayout.catalog.kenney_index import placement_category

    child_cat = placement_category(child_model_id)
    parent_cat = placement_category(parent_model_id)
    return valid_stack_parent(child_cat, parent_cat, mode)


def wall_distance_exempt(category: str) -> bool:
    cfg = load_config()
    exempt = (cfg.get("wall_distance_m") or {}).get("exempt") or []
    return category in exempt


def wall_distance_bounds_m(
    category: str,
    *,
    overrides: ThetaOverrides = None,
) -> tuple[float, float | None]:
    """Return (min_m, max_m) from nearest room wall; max_m None = no upper bound."""
    if wall_distance_exempt(category):
        return 0.0, None
    cfg = load_config()
    section = cfg.get("wall_distance_m") or {}
    defaults = section.get("defaults") or {}
    default_min = float(defaults.get("min", 0.0))
    default_max_raw = defaults.get("max")
    default_max = None if default_max_raw is None else float(default_max_raw)

    cats = section.get("categories") or {}
    explicit = cats.get(category)
    if explicit:
        min_m = float(explicit.get("min", default_min))
        max_raw = explicit.get("max")
        max_m = default_max if max_raw is None else float(max_raw)
    else:
        min_m = default_min
        max_m = default_max

    min_override = _override_value(overrides, wall_theta_key(category, "min_m"))
    max_override = _override_value(overrides, wall_theta_key(category, "max_m"))
    if min_override is not None:
        min_m = min_override
    if max_override is not None:
        max_m = max_override
    return min_m, max_m


def wall_distance_bounds_centi(
    category: str,
    cell_m: float,
    *,
    overrides: ThetaOverrides = None,
) -> tuple[int, int | None]:
    min_m, max_m = wall_distance_bounds_m(category, overrides=overrides)
    min_c = int(round(min_m / cell_m)) * 100
    max_c = None if max_m is None else int(round(max_m / cell_m)) * 100
    return min_c, max_c


def front_clearance_m(category: str) -> float | None:
    """Return required clear depth in front of category, or None if not configured."""
    cfg = load_config()
    anchors = (cfg.get("front_clearance_m") or {}).get("anchors") or {}
    if category not in anchors:
        return None
    return float(anchors[category])


def front_clearance_cells(category: str, cell_m: float) -> int | None:
    clearance_m = front_clearance_m(category)
    if clearance_m is None:
        return None
    return max(1, int(round(clearance_m / cell_m)))


def front_clearance_global_exempt(category: str) -> bool:
    cfg = load_config()
    exempt = (cfg.get("front_clearance_m") or {}).get("global_exempt") or []
    return category in exempt


def blocker_allowed_in_front_clearance(blocker_cat: str, anchor_cat: str) -> bool:
    """True when blocker may occupy anchor's front zone (e.g. chair at desk)."""
    if front_clearance_global_exempt(blocker_cat):
        return True
    cfg = load_config()
    allowed = (cfg.get("front_clearance_m") or {}).get("allowed_blockers") or {}
    anchor_list = allowed.get(blocker_cat) or []
    return anchor_cat in anchor_list
