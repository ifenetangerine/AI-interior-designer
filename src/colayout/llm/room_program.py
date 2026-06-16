"""Room density tiers, furniture programs, and design-principles excerpts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)

DensityTier = Literal["compact", "standard", "spacious"]

ROOT = Path(__file__).resolve().parents[3]
PRINCIPLES_PATH = ROOT / "design_principles.md"

COMPACT_AREA_M2 = 12.0
SPACIOUS_AREA_M2 = 25.0
FCR_MIN = 0.35
FCR_MAX = 0.45

PIECE_BOUNDS: dict[str, dict[DensityTier, tuple[int, int]]] = {
    "bedroom": {
        "compact": (5, 8),
        "standard": (9, 12),
        "spacious": (9, 14),
    },
    "living_room": {
        "compact": (5, 7),
        "standard": (6, 9),
        "spacious": (10, 14),
    },
    "kitchen": {
        "compact": (10, 12),
        "standard": (11, 14),
        "spacious": (14, 18),
    },
}

ANCHOR_BY_ROOM: dict[str, str] = {
    "bedroom": "bed",
    "living_room": "tv",
    "kitchen": "dining_table",
    "dining": "dining_table",
}

# Kenney roles that must appear in every layout (stove = stovetop/oven).
REQUIRED_ROLES: dict[str, list[tuple[str, int]]] = {
    "bedroom": [
        ("bed", 1),
        ("desk", 1),
        ("chair", 1),
        ("wardrobe", 1),
        ("nightstand", 1),
    ],
    "kitchen": [
        ("dining_table", 1),
        ("sink", 1),
        ("stove", 1),
        ("fridge", 1),
        ("chair", 1),
        ("counter_segment", 2),
    ],
    "living_room": [
        ("sofa", 1),
        ("coffee_table", 1),
        ("tv", 1),
    ],
}

RECOMMENDED_ROLES_BY_TIER: dict[str, dict[DensityTier, list[tuple[str, int]]]] = {
    "living_room": {
        "standard": [("side_table", 1), ("chair", 1)],
        "spacious": [("side_table", 1), ("chair", 1), ("bookshelf", 1), ("rug", 1)],
    },
    "bedroom": {
        "standard": [("lamp", 1)],
        "spacious": [("lamp", 1), ("plant", 1)],
    },
}

DECOR_BY_TIER: dict[str, dict[DensityTier, list[tuple[str, int]]]] = {
    "bedroom": {
        "standard": [("lamp", 1)],
        "spacious": [("lamp", 1), ("plant", 1)],
    },
    "living_room": {
        "standard": [("rug", 1), ("lamp", 1)],
        "spacious": [("bookshelf", 1), ("plant", 1), ("lamp", 2)],
    },
    "kitchen": {
        "spacious": [("plant", 1)],
    },
}

MIN_FLOOR_COVERAGE: dict[str, dict[DensityTier, float]] = {
    "living_room": {"standard": 0.15, "spacious": 0.12},
}

COUNTER_SEGMENT_ROLES = frozenset(
    {"counter_end", "counter_bar", "counter_base"}
)

FLOATING_ANCHOR_ROLES = frozenset({"dining_table", "coffee_table"})

ROOM_SECTION_HEADINGS: dict[str, str] = {
    "bedroom": "## Bedrooms",
    "living_room": "## Living Rooms",
    "kitchen": "## Kitchens",
    "dining": "## Dining Zones",
}

STORAGE_CATEGORIES = frozenset(
    {"wardrobe", "dresser", "fridge", "counter", "tv_stand"}
)

WALL_DEFAULTS: dict[str, str | None] = {
    "bed": "west",
    "sofa": "south",
    "tv_stand": "north",
    "tv": "north",
    "storage_cabinet": "north",
    "wardrobe": "north",
    "fridge": "north",
    "counter": "north",
    "desk": "east",
    "dining_table": None,
    "coffee_table": None,
}

WALL_HUG_CATEGORIES = frozenset(
    {"bed", "wardrobe", "dresser", "fridge", "counter", "tv_stand", "desk"}
)

def staging_prompt(room_type: str, tier: DensityTier) -> str:
    """Tier-based staging and recommended roles for placement prompts."""
    lines: list[str] = []
    rec = RECOMMENDED_ROLES_BY_TIER.get(room_type, {}).get(tier, [])
    if rec:
        lines.append(f"Recommended for {tier} {room_type.replace('_', ' ')} (include when possible):")
        for role, count in rec:
            lines.append(f"  - {role.replace('_', ' ')}: {count}")
    decor = DECOR_BY_TIER.get(room_type, {}).get(tier, [])
    if decor:
        lines.append(f"Staging decor for {tier} tier:")
        for role, count in decor:
            lines.append(f"  - {role}: {count}")
    return "\n".join(lines)


def room_area_m2(room: RoomSpec) -> float:
    return room.width_m * room.length_m


def floor_coverage_ratio_bounds(area_m2: float) -> tuple[float, float]:
    """Target combined furniture footprint area for LLM layouts (35–45% FCR)."""
    return area_m2 * FCR_MIN, area_m2 * FCR_MAX


def density_tier(area_m2: float) -> DensityTier:
    if area_m2 < COMPACT_AREA_M2:
        return "compact"
    if area_m2 > SPACIOUS_AREA_M2:
        return "spacious"
    return "standard"


def furniture_count_bounds(room_type: str, tier: DensityTier) -> tuple[int, int]:
    by_type = PIECE_BOUNDS.get(room_type, PIECE_BOUNDS["bedroom"])
    return by_type.get(tier, by_type["standard"])


def max_furniture_pieces(room: RoomSpec) -> int:
    tier = density_tier(room_area_m2(room))
    return furniture_count_bounds(room.type, tier)[1]


def anchor_category(room_type: str) -> str:
    return ANCHOR_BY_ROOM.get(room_type, "bed")


ANCHOR_WALL_BY_ROOM: dict[str, str] = {
    "bedroom": "west",
    "living_room": "south",
}


def required_furniture_prompt(room_type: str) -> str:
    specs = REQUIRED_ROLES.get(room_type, [])
    if not specs:
        return ""
    parts = ["Required furniture (must all appear):"]
    for role, count in specs:
        label = role.replace("_", " ")
        if role == "counter_segment":
            label = "counter segments (bar/cabinet)"
        if role == "stove":
            label = "stove/stovetop (oven)"
        parts.append(f"  - {label}: {count}")
    parts.append("All other catalog pieces are optional.")
    return "\n".join(parts)


def anchor_placement_guidance(room: RoomSpec | str) -> str:
    from colayout.llm.anchor_structure import anchor_structure_guidance

    if isinstance(room, str):
        # Legacy callers: assume standard-tier room for static type-only hints.
        stub = RoomSpec(id="x", type=room, width_m=16.0, length_m=14.0)
        return anchor_structure_guidance(stub)
    return anchor_structure_guidance(room)


def placement_wall_guidance(room: RoomSpec) -> str:
    """Concrete placement instructions from the principle registry."""
    from colayout.design.principle_registry import placement_guidance_for_room

    return placement_guidance_for_room(room)


def default_wall_for_category(category: str, room_type: str) -> str | None:
    if category == "desk":
        return "east" if room_type == "bedroom" else "west"
    return WALL_DEFAULTS.get(category)


def principles_excerpt(room_type: str, max_chars: int = 5500) -> str:
    if not PRINCIPLES_PATH.is_file():
        return ""
    text = PRINCIPLES_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    classical_start = _find_line(lines, "## Classical Design Principles")
    universal_start = _find_line(lines, "## Universal Principles")
    start = classical_start if classical_start >= 0 else universal_start
    room_heading = ROOM_SECTION_HEADINGS.get(room_type, "## Bedrooms")
    room_start = _find_line(lines, room_heading)
    if start < 0:
        return ""
    if room_start < 0:
        room_start = len(lines)
    room_end = _next_section(lines, room_start + 1)
    chunk = "\n".join(lines[start:room_end])
    if len(chunk) > max_chars:
        chunk = chunk[: max_chars - 3] + "..."
    return chunk


def _find_line(lines: list[str], heading: str) -> int:
    for i, line in enumerate(lines):
        if line.strip() == heading:
            return i
    return -1


def _next_section(lines: list[str], start: int) -> int:
    for i in range(start, len(lines)):
        if lines[i].startswith("## ") and not lines[i].startswith("### "):
            return i
    return len(lines)


def find_items_by_category(
    furniture: list[FurnitureItem], category: str
) -> list[FurnitureItem]:
    return [f for f in furniture if f.category == category]


def constraint_referenced_ids(constraints: list[FurnitureConstraint]) -> set[str]:
    refs: set[str] = set()
    for c in constraints:
        if c.furniture:
            refs.add(c.furniture)
        if c.furniture_a:
            refs.add(c.furniture_a)
        if c.furniture_b:
            refs.add(c.furniture_b)
        for fid in c.furniture_ids:
            refs.add(fid)
    return refs


def _role_counts_from_model_ids(model_ids: list[str]) -> dict[str, int]:
    from colayout.catalog.kenney_index import role_for_model

    counts: dict[str, int] = {}
    counter_segments = 0
    for mid in model_ids:
        role = role_for_model(mid)
        counts[role] = counts.get(role, 0) + 1
        if role in COUNTER_SEGMENT_ROLES:
            counter_segments += 1
    if counter_segments:
        counts["counter_segment"] = counter_segments
    return counts


def _role_counts_from_furniture(furniture: list[FurnitureItem]) -> dict[str, int]:
    return _role_counts_from_model_ids(
        [f.model_id for f in furniture if f.model_id]
    )


def check_required_furniture(
    model_ids: list[str],
    room_type: str,
) -> list[str]:
    """Return blocking errors for missing required roles."""
    errors: list[str] = []
    counts = _role_counts_from_model_ids(model_ids)
    for role, min_count in REQUIRED_ROLES.get(room_type, []):
        have = counts.get(role, 0)
        if have < min_count:
            label = role.replace("_", " ")
            errors.append(
                f"missing required {label}: need {min_count}, have {have}"
            )
    return errors


def check_min_piece_count(
    furniture: list[FurnitureItem],
    room: RoomSpec,
) -> str | None:
    tier = density_tier(room_area_m2(room))
    min_pieces, _ = furniture_count_bounds(room.type, tier)
    if len(furniture) < min_pieces:
        return (
            f"furniture count {len(furniture)} below minimum {min_pieces} "
            f"for {tier} {room.type} ({room_area_m2(room):.1f} m²)"
        )
    required_errs = check_required_furniture(
        [f.model_id for f in furniture if f.model_id],
        room.type,
    )
    if required_errs:
        return required_errs[0]
    return None


def check_desk_chair_balance(furniture: list[FurnitureItem]) -> str | None:
    n_desk = len(find_items_by_category(furniture, "desk"))
    n_chair = len(find_items_by_category(furniture, "chair"))
    if n_desk > n_chair:
        return (
            f"need at least one chair per desk ({n_desk} desks, {n_chair} chairs)"
        )
    return None


def check_recommended_roles(
    model_ids: list[str],
    room: RoomSpec,
) -> list[str]:
    """Warnings when tier-based recommended roles are missing."""
    tier = density_tier(room_area_m2(room))
    specs = RECOMMENDED_ROLES_BY_TIER.get(room.type, {}).get(tier, [])
    if not specs:
        return []
    counts = _role_counts_from_model_ids(model_ids)
    warnings: list[str] = []
    for role, min_count in specs:
        have = counts.get(role, 0)
        if have < min_count:
            label = role.replace("_", " ")
            warnings.append(
                f"(warning) missing recommended {label}: need {min_count}, have {have}"
            )
    return warnings


def check_decor_staging(
    model_ids: list[str],
    room: RoomSpec,
) -> list[str]:
    """Warnings when tier-based decor staging roles are missing."""
    tier = density_tier(room_area_m2(room))
    specs = DECOR_BY_TIER.get(room.type, {}).get(tier, [])
    if not specs:
        return []
    counts = _role_counts_from_model_ids(model_ids)
    warnings: list[str] = []
    for role, min_count in specs:
        have = counts.get(role, 0)
        if have < min_count:
            warnings.append(
                f"(warning) missing staging {role}: need {min_count}, have {have}"
            )
    return warnings


def check_floor_coverage_min(
    furniture: list[FurnitureItem],
    room: RoomSpec,
) -> str | None:
    """Warn when floor coverage is below tier minimum for a room type."""
    tier = density_tier(room_area_m2(room))
    min_ratio = MIN_FLOOR_COVERAGE.get(room.type, {}).get(tier)
    if min_ratio is None or not furniture:
        return None
    room_area = room.width_m * room.length_m
    if room_area <= 0:
        return None
    furniture_area = sum(
        (f.width_m or 0) * (f.length_m or 0) for f in furniture
    )
    ratio = furniture_area / room_area
    if ratio < min_ratio:
        return (
            f"(warning) furniture footprint {ratio:.0%} below {min_ratio:.0%} "
            f"target for {tier} {room.type} — add accent seating, rug, or storage"
        )
    return None


def check_dining_seating(
    furniture: list[FurnitureItem],
    room: RoomSpec,
) -> str | None:
    tables = find_items_by_category(furniture, "dining_table")
    if not tables:
        return None
    chairs = find_items_by_category(furniture, "chair")
    desks = find_items_by_category(furniture, "desk")
    dining_chairs = len(chairs) - len(desks)
    tier = density_tier(room_area_m2(room))
    if tier != "compact" and dining_chairs < 2:
        return (
            f"dining_table needs at least 2 chairs (have {dining_chairs} "
            f"after desk pairing)"
        )
    return None
