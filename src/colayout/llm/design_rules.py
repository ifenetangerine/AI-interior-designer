"""Room-type design rules and furniture category normalization."""

from __future__ import annotations

from colayout.catalog.kenney_index import footprint_for_model, placement_category
from colayout.llm.role_constraints import apply_role_constraints
from colayout.llm.room_program import (
    FUNCTIONAL_GROUPS,
    default_wall_for_category,
    find_items_by_category,
)
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    RoomSceneGraph,
)

ALLOWED_CATEGORIES = frozenset(
    {
        "bed",
        "chair",
        "desk",
        "sofa",
        "wardrobe",
        "tv_stand",
        "coffee_table",
        "dining_table",
        "side_table",
        "counter",
        "fridge",
        "nightstand",
        "dresser",
    }
)

CATEGORY_ALIASES: dict[str, str] = {
    "table": "dining_table",
    "tables": "dining_table",
    "fan": "side_table",
    "lamp": "side_table",
    "night_stand": "nightstand",
    "closet": "wardrobe",
    "tv": "tv_stand",
    "television": "tv_stand",
    "couch": "sofa",
    "stove": "counter",
    "sink": "counter",
}

_LINK_BY_PAIR: dict[tuple[str, str], object] = {
    (link.from_cat, link.to_cat): link for link in FUNCTIONAL_GROUPS
}


def normalize_category(raw: str) -> str | None:
    key = raw.strip().lower().replace(" ", "_")
    if key in ALLOWED_CATEGORIES:
        return key
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    return None


def _ensure_catalog_fields(graph: RoomSceneGraph) -> RoomSceneGraph:
    """Fill category and footprints from model_id when missing (pre-validate enrich)."""
    updated: list = []
    for f in graph.furniture:
        if f.model_id:
            w, d = footprint_for_model(f.model_id)
            updated.append(
                f.model_copy(
                    update={
                        "category": f.category or placement_category(f.model_id),
                        "width_m": f.width_m if f.width_m is not None else w,
                        "length_m": f.length_m if f.length_m is not None else d,
                    }
                )
            )
        else:
            updated.append(f)
    return graph.model_copy(update={"furniture": updated})


def enrich_scene_graph(graph: RoomSceneGraph) -> RoomSceneGraph:
    """Add walls, functional links, and relational constraints."""
    graph = _ensure_catalog_fields(graph)
    furniture = graph.furniture
    existing = {
        (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        for c in graph.constraints
    }
    walled: set[str] = {
        c.furniture
        for c in graph.constraints
        if c.type == ConstraintType.AGAINST_WALL and c.furniture
    }

    def add(c: FurnitureConstraint) -> None:
        key = (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        if key not in existing:
            graph.constraints.append(c)
            existing.add(key)

    for f in furniture:
        if f.id in walled:
            continue
        if f.category in (
            "bed",
            "sofa",
            "wardrobe",
            "desk",
            "counter",
            "fridge",
            "tv_stand",
            "dining_table",
        ):
            wall = default_wall_for_category(f.category, graph.room_type)
            if wall:
                add(
                    FurnitureConstraint(
                        type=ConstraintType.AGAINST_WALL,
                        furniture=f.id,
                        wall=wall,
                    )
                )
                walled.add(f.id)

    for link in FUNCTIONAL_GROUPS:
        from_items = find_items_by_category(furniture, link.from_cat)
        to_items = find_items_by_category(furniture, link.to_cat)
        if not from_items or not to_items:
            continue
        for fa in from_items:
            fb = to_items[0]
            if fa.id == fb.id:
                continue
            if link.facing:
                add(
                    FurnitureConstraint(
                        type=ConstraintType.FACING,
                        furniture_a=fa.id,
                        furniture_b=fb.id,
                    )
                )
            if link.adjacent:
                add(
                    FurnitureConstraint(
                        type=ConstraintType.ADJACENT,
                        furniture_a=fa.id,
                        furniture_b=fb.id,
                    )
                )

    graph = apply_role_constraints(graph)

    weights = graph.weights.model_copy(
        update={"bal": min(graph.weights.bal, 0.05), "walk": max(graph.weights.walk, 0.6)}
    )
    return graph.model_copy(update={"weights": weights})
