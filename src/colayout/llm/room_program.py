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

PIECE_BOUNDS: dict[str, dict[DensityTier, tuple[int, int]]] = {
    "bedroom": {
        "compact": (5, 7),
        "standard": (5, 8),
        "spacious": (6, 10),
    },
    "living_room": {
        "compact": (3, 5),
        "standard": (5, 7),
        "spacious": (6, 10),
    },
    "kitchen": {
        "compact": (7, 10),
        "standard": (8, 12),
        "spacious": (10, 14),
    },
}

ANCHOR_BY_ROOM: dict[str, str] = {
    "bedroom": "bed",
    "living_room": "sofa",
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
        ("tv_stand", 1),
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

# IP hard connectivity: these must sit near another placed piece.
CONNECTIVITY_CATEGORIES = frozenset(
    {"chair", "nightstand", "side_table", "coffee_table"}
)

DINING_SURROUND_OFFSETS: list[tuple[float, float]] = [
    (0.0, -0.75),
    (0.0, 0.75),
    (-0.75, 0.0),
    (0.75, 0.0),
]


@dataclass(frozen=True)
class FunctionalLink:
    from_cat: str
    to_cat: str
    facing: bool = False
    adjacent: bool = False


FUNCTIONAL_GROUPS: list[FunctionalLink] = [
    FunctionalLink("sofa", "tv_stand", facing=True),
    FunctionalLink("coffee_table", "sofa", adjacent=True),
    FunctionalLink("side_table", "sofa", adjacent=True),
]

PULL_OUT_RELATIVE: list[tuple[str, str, float, float]] = [
    ("chair", "desk", 0.0, -0.7),
    ("chair", "dining_table", 0.0, -0.75),
]


def apply_relational_constraints(graph: RoomSceneGraph) -> RoomSceneGraph:
    """Add flank, desk-chair pairs, and dining surround constraints."""
    existing = {
        (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        for c in graph.constraints
    }

    def add(c: FurnitureConstraint) -> None:
        key = (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        if key not in existing:
            graph.constraints.append(c)
            existing.add(key)

    furniture = graph.furniture
    beds = find_items_by_category(furniture, "bed")
    desks = find_items_by_category(furniture, "desk")
    chairs = find_items_by_category(furniture, "chair")
    nightstands = find_items_by_category(furniture, "nightstand")
    tables = find_items_by_category(furniture, "dining_table")

    for bed in beds:
        if len(nightstands) >= 2:
            add(
                FurnitureConstraint(
                    type=ConstraintType.FLANK,
                    furniture_a=nightstands[0].id,
                    furniture_b=bed.id,
                    side="left",
                )
            )
            add(
                FurnitureConstraint(
                    type=ConstraintType.FLANK,
                    furniture_a=nightstands[1].id,
                    furniture_b=bed.id,
                    side="right",
                )
            )
        elif len(nightstands) == 1:
            side = "left"
            if nightstands[0].id.endswith("_r"):
                side = "right"
            add(
                FurnitureConstraint(
                    type=ConstraintType.FLANK,
                    furniture_a=nightstands[0].id,
                    furniture_b=bed.id,
                    side=side,
                )
            )

    desk_chairs = chairs[: len(desks)]
    for desk, chair in zip(desks, desk_chairs):
        add(
            FurnitureConstraint(
                type=ConstraintType.IN_FRONT_OF,
                furniture_a=chair.id,
                furniture_b=desk.id,
                distance_m=0.7,
            )
        )
        add(
            FurnitureConstraint(
                type=ConstraintType.FACING,
                furniture_a=chair.id,
                furniture_b=desk.id,
            )
        )

    for table in tables:
        add(
            FurnitureConstraint(
                type=ConstraintType.SEATS_AROUND,
                furniture=table.id,
                min_seats=2,
            )
        )

    return graph


def apply_living_room_constraints(graph: RoomSceneGraph) -> RoomSceneGraph:
    """Sofa/TV/coffee/accent links for living rooms on the refine path."""
    if graph.room_type != "living_room":
        return graph

    existing = {
        (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        for c in graph.constraints
    }

    def add(c: FurnitureConstraint) -> None:
        key = (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        if key not in existing:
            graph.constraints.append(c)
            existing.add(key)

    furniture = graph.furniture
    sofas = find_items_by_category(furniture, "sofa")
    tvs = find_items_by_category(furniture, "tv_stand")
    coffee = find_items_by_category(furniture, "coffee_table")
    side_tables = find_items_by_category(furniture, "side_table")
    chairs = find_items_by_category(furniture, "chair")

    if sofas and tvs:
        add(
            FurnitureConstraint(
                type=ConstraintType.FACING,
                furniture_a=sofas[0].id,
                furniture_b=tvs[0].id,
            )
        )
    if sofas and coffee:
        add(
            FurnitureConstraint(
                type=ConstraintType.ADJACENT,
                furniture_a=coffee[0].id,
                furniture_b=sofas[0].id,
            )
        )
    if sofas and side_tables:
        add(
            FurnitureConstraint(
                type=ConstraintType.ADJACENT,
                furniture_a=side_tables[0].id,
                furniture_b=sofas[0].id,
            )
        )
    if sofas and chairs:
        accent = chairs[0]
        add(
            FurnitureConstraint(
                type=ConstraintType.FACING,
                furniture_a=accent.id,
                furniture_b=sofas[0].id,
            )
        )
        if coffee:
            add(
                FurnitureConstraint(
                    type=ConstraintType.ADJACENT,
                    furniture_a=accent.id,
                    furniture_b=coffee[0].id,
                )
            )

    return graph


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


def anchor_placement_guidance(room_type: str) -> str:
    if room_type == "bedroom":
        return (
            "Bedroom anchors:\n"
            "  1. placement_order 1 = bed (headboard on west wall). "
            "Implies nightstands flanking the bed on both sides.\n"
            "  2. desk on east wall with chair directly in front of / beside it.\n"
            "  Required: bed, desk, chair, wardrobe, nightstand."
        )
    if room_type == "living_room":
        return (
            "Living room anchor:\n"
            "  placement_order 1 = main sofa (back on south wall, facing north).\n"
            "  Implies: coffee table in front of sofa; TV on north wall facing sofa; "
            "side table at sofa arm; accent chair completing the conversation group.\n"
            "  Standard tier: include rug under coffee table and floor lamp beside seating.\n"
            "  Required: sofa, coffee table, TV stand."
        )
    if room_type == "kitchen":
        return (
            "Kitchen anchors:\n"
            "  placement_order 1 = dining table (center of dining zone). "
            "Implies dining chairs on all sides where space permits.\n"
            "  placement_order 2 = sink on north wall. "
            "Implies counter segments, cabinets, stove/stovetop, and fridge "
            "surrounding or adjacent to the sink run along the wall.\n"
            "  Required: dining table, sink, stove, fridge, dining chair, "
            "at least 2 counter segments."
        )
    return ""


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


def expand_baseline_for_room(baseline: dict, room: RoomSpec) -> dict:
    """Add furniture by density tier so large rooms are not under-furnished."""
    import copy

    data = copy.deepcopy(baseline)
    furniture: list[dict] = list(data.get("furniture", []))
    constraints: list[dict] = list(data.get("constraints", []))
    existing_ids = {f["id"] for f in furniture}
    tier = density_tier(room_area_m2(room))
    min_pieces, _ = furniture_count_bounds(room.type, tier)

    def add_piece(
        fid: str,
        category: str,
        width_m: float,
        length_m: float,
    ) -> None:
        if fid in existing_ids:
            return
        furniture.append(
            {
                "id": fid,
                "category": category,
                "width_m": width_m,
                "length_m": length_m,
            }
        )
        existing_ids.add(fid)

    def add_constraint(c: dict) -> None:
        key = (
            c["type"],
            c.get("furniture"),
            c.get("furniture_a"),
            c.get("furniture_b"),
            c.get("side"),
        )
        seen = {
            (
                x["type"],
                x.get("furniture"),
                x.get("furniture_a"),
                x.get("furniture_b"),
                x.get("side"),
            )
            for x in constraints
        }
        if key not in seen:
            constraints.append(c)

    if room.type == "bedroom":
        if tier in ("standard", "spacious"):
            add_piece("nightstand_l", "nightstand", 0.5, 0.4)
            add_piece("nightstand_r", "nightstand", 0.5, 0.4)
            add_constraint(
                {
                    "type": "flank",
                    "furniture_a": "nightstand_l",
                    "furniture_b": "bed",
                    "side": "left",
                }
            )
            add_constraint(
                {
                    "type": "flank",
                    "furniture_a": "nightstand_r",
                    "furniture_b": "bed",
                    "side": "right",
                }
            )
        if tier == "spacious":
            add_piece("dresser", "dresser", 1.0, 0.5)
            add_piece("reading_chair", "chair", 0.6, 0.6)
            add_piece("side_table", "side_table", 0.5, 0.5)
            add_constraint(
                {
                    "type": "adjacent",
                    "furniture_a": "reading_chair",
                    "furniture_b": "side_table",
                }
            )
            add_constraint(
                {
                    "type": "against_wall",
                    "furniture": "dresser",
                    "wall": "north",
                }
            )
        while len(furniture) < min_pieces and tier != "compact":
            add_piece(f"extra_{len(furniture)}", "side_table", 0.4, 0.4)

    elif room.type == "living_room":
        if tier in ("standard", "spacious"):
            add_piece("side_table", "side_table", 0.5, 0.5)
        if tier == "spacious":
            add_piece("accent_chair", "chair", 0.7, 0.7)
            add_piece("bookshelf", "wardrobe", 1.0, 0.4)
            add_constraint(
                {
                    "type": "facing",
                    "furniture_a": "accent_chair",
                    "furniture_b": "sofa",
                }
            )
            add_constraint(
                {
                    "type": "adjacent",
                    "furniture_a": "accent_chair",
                    "furniture_b": "coffee_table",
                }
            )
            add_constraint(
                {
                    "type": "against_wall",
                    "furniture": "bookshelf",
                    "wall": "north",
                }
            )

    elif room.type == "kitchen":
        if tier in ("standard", "spacious"):
            add_piece("dining_table", "dining_table", 1.2, 0.8)
            for cid in ("dining_chair_1", "dining_chair_2", "dining_chair_3", "dining_chair_4"):
                add_piece(cid, "chair", 0.5, 0.5)
            add_constraint({"type": "seats_around", "furniture": "dining_table", "min_seats": 2})

    data["furniture"] = furniture
    data["constraints"] = constraints
    weights = data.get("weights") or {}
    weights.setdefault("rel", 1.0)
    weights["bal"] = 0.0
    weights["walk"] = max(float(weights.get("walk", 0.7)), 0.6)
    data["weights"] = weights
    return data


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


def orphan_furniture_ids(
    furniture: list[FurnitureItem],
    constraints: list[FurnitureConstraint],
    room_type: str,
) -> list[str]:
    refs = constraint_referenced_ids(constraints)
    anchor = anchor_category(room_type)
    orphans: list[str] = []
    for f in furniture:
        if f.category == anchor:
            continue
        if f.category in STORAGE_CATEGORIES:
            continue
        if f.id not in refs:
            orphans.append(f.id)
    return orphans


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
