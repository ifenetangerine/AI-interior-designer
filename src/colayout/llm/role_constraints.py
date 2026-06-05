"""Role-based relational constraints from catalog model_ids."""

from __future__ import annotations

from colayout.catalog.kenney_index import (
    CHAIN_ORDER,
    COUNTER_RUN_ROLES,
    role_for_model,
)
from colayout.llm.room_program import (
    apply_relational_constraints,
    default_wall_for_category,
    find_items_by_category,
)
from colayout.schemas.scene import (
    ConstraintType,
    FurnitureConstraint,
    FurnitureItem,
    RoomSceneGraph,
)


def _role(item: FurnitureItem) -> str:
    if item.model_id:
        return role_for_model(item.model_id)
    return item.category or "decor"


def find_items_by_role(
    furniture: list[FurnitureItem], role: str
) -> list[FurnitureItem]:
    return [f for f in furniture if _role(f) == role]


def _counter_run_order(items: list[FurnitureItem]) -> list[FurnitureItem]:
    return sorted(
        items,
        key=lambda f: CHAIN_ORDER.get(_role(f), 99),
    )


def apply_role_constraints(graph: RoomSceneGraph) -> RoomSceneGraph:
    """Add walls, functional groups, counter chains, and relational rules."""
    furniture = graph.furniture
    room_type = graph.room_type
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
        key = (
            c.type,
            c.furniture,
            c.furniture_a,
            c.furniture_b,
            c.side,
            tuple(c.furniture_ids),
        )
        if key not in existing:
            graph.constraints.append(c)
            existing.add(key)

    wall_storage = (
        "bed",
        "sofa",
        "wardrobe",
        "desk",
        "counter",
        "fridge",
        "tv_stand",
        "dining_table",
    )
    for f in furniture:
        if f.id in walled or not f.category:
            continue
        if f.category in wall_storage:
            wall = default_wall_for_category(f.category, room_type)
            if wall:
                add(
                    FurnitureConstraint(
                        type=ConstraintType.AGAINST_WALL,
                        furniture=f.id,
                        wall=wall,
                    )
                )
                walled.add(f.id)
        if _role(f) == "bookshelf":
            add(
                FurnitureConstraint(
                    type=ConstraintType.AGAINST_WALL,
                    furniture=f.id,
                    wall=default_wall_for_category("wardrobe", room_type) or "north",
                )
            )
            walled.add(f.id)

    # Kitchen counter run
    if room_type == "kitchen":
        run_items = [
            f
            for f in furniture
            if _role(f) in COUNTER_RUN_ROLES
        ]
        if len(run_items) >= 2:
            ordered = _counter_run_order(run_items)
            chain_ids = [f.id for f in ordered]
            wall = default_wall_for_category("counter", room_type) or "north"
            has_chain = any(
                c.type == ConstraintType.ADJACENT_CHAIN
                for c in graph.constraints
            )
            if not has_chain:
                add(
                    FurnitureConstraint(
                        type=ConstraintType.ADJACENT_CHAIN,
                        furniture_ids=chain_ids,
                        wall=wall,
                    )
                )
            for f in ordered:
                if f.id not in walled:
                    add(
                        FurnitureConstraint(
                            type=ConstraintType.AGAINST_WALL,
                            furniture=f.id,
                            wall=wall,
                        )
                    )
                    walled.add(f.id)
        fridges = find_items_by_role(furniture, "fridge")
        if fridges and run_items:
            run_end = _counter_run_order(run_items)[-1]
            add(
                FurnitureConstraint(
                    type=ConstraintType.ADJACENT,
                    furniture_a=fridges[0].id,
                    furniture_b=run_end.id,
                )
            )
            if fridges[0].id not in walled:
                wall = default_wall_for_category("fridge", room_type) or "north"
                add(
                    FurnitureConstraint(
                        type=ConstraintType.AGAINST_WALL,
                        furniture=fridges[0].id,
                        wall=wall,
                    )
                )
                walled.add(fridges[0].id)

    # Bar stools at counter bar
    bars = find_items_by_role(furniture, "counter_bar")
    stools = find_items_by_role(furniture, "bar_stool")
    for stool, bar in zip(stools, bars):
        add(
            FurnitureConstraint(
                type=ConstraintType.IN_FRONT_OF,
                furniture_a=stool.id,
                furniture_b=bar.id,
                distance_m=0.6,
            )
        )

    # Rug under coffee table or room center
    rugs = find_items_by_role(furniture, "rug")
    coffee = find_items_by_category(furniture, "coffee_table")
    for rug in rugs:
        if coffee:
            add(
                FurnitureConstraint(
                    type=ConstraintType.ADJACENT,
                    furniture_a=rug.id,
                    furniture_b=coffee[0].id,
                )
            )
        else:
            add(
                FurnitureConstraint(
                    type=ConstraintType.RELATIVE_POSITION,
                    furniture_a=rug.id,
                    furniture_b=furniture[0].id,
                    offset_i=0.0,
                    offset_j=0.0,
                )
            )

    graph = apply_relational_constraints(graph)

    # Sofa / TV / coffee (functional groups handled in design_rules enrich)
    sofas = find_items_by_category(furniture, "sofa")
    tvs = find_items_by_category(furniture, "tv_stand")
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

    return graph


def apply_decor_constraints(graph: RoomSceneGraph) -> RoomSceneGraph:
    """Auto-link lamps, plants, rugs so decor is orphan-safe on refine path."""
    furniture = graph.furniture
    existing = {
        (c.type, c.furniture, c.furniture_a, c.furniture_b, c.side, tuple(c.furniture_ids))
        for c in graph.constraints
    }

    def add(c: FurnitureConstraint) -> None:
        key = (
            c.type,
            c.furniture,
            c.furniture_a,
            c.furniture_b,
            c.side,
            tuple(c.furniture_ids),
        )
        if key not in existing:
            graph.constraints.append(c)
            existing.add(key)

    nightstands = find_items_by_category(furniture, "nightstand")
    side_tables = find_items_by_category(furniture, "side_table")
    sofas = find_items_by_category(furniture, "sofa")
    chairs = find_items_by_category(furniture, "chair")
    coffee = find_items_by_category(furniture, "coffee_table")
    bookshelves = find_items_by_role(furniture, "bookshelf")

    from colayout.catalog.kenney_index import surface_kind_for_model

    table_lamp_targets = nightstands + side_tables + coffee
    floor_lamps: list[FurnitureItem] = []
    surface_lamps: list[FurnitureItem] = []
    for item in furniture:
        if _role(item) != "lamp":
            continue
        mid = item.model_id or ""
        if surface_kind_for_model(mid) == "floor":
            floor_lamps.append(item)
        elif surface_kind_for_model(mid) == "table":
            surface_lamps.append(item)

    for lamp, target in zip(surface_lamps, table_lamp_targets):
        add(
            FurnitureConstraint(
                type=ConstraintType.ON_TOP_OF,
                furniture_a=lamp.id,
                furniture_b=target.id,
            )
        )

    seat_targets = sofas + chairs[:1]
    for lamp, target in zip(floor_lamps, seat_targets):
        add(
            FurnitureConstraint(
                type=ConstraintType.ADJACENT,
                furniture_a=lamp.id,
                furniture_b=target.id,
            )
        )

    plants = find_items_by_role(furniture, "plant")
    for plant in plants:
        if bookshelves:
            add(
                FurnitureConstraint(
                    type=ConstraintType.ADJACENT,
                    furniture_a=plant.id,
                    furniture_b=bookshelves[0].id,
                )
            )
        elif sofas:
            wall = default_wall_for_category("wardrobe", graph.room_type) or "north"
            add(
                FurnitureConstraint(
                    type=ConstraintType.AGAINST_WALL,
                    furniture=plant.id,
                    wall=wall,
                )
            )

    rugs = find_items_by_role(furniture, "rug")
    for rug in rugs:
        if coffee:
            add(
                FurnitureConstraint(
                    type=ConstraintType.UNDER,
                    furniture_a=rug.id,
                    furniture_b=coffee[0].id,
                )
            )
        elif sofas:
            add(
                FurnitureConstraint(
                    type=ConstraintType.UNDER,
                    furniture_a=rug.id,
                    furniture_b=sofas[0].id,
                )
            )

    for shelf in bookshelves:
        wall = default_wall_for_category("wardrobe", graph.room_type) or "north"
        add(
            FurnitureConstraint(
                type=ConstraintType.AGAINST_WALL,
                furniture=shelf.id,
                wall=wall,
            )
        )

    return graph
