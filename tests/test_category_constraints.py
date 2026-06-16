"""Tests for category placement constraint config."""

from __future__ import annotations

import math

from colayout.placement.category_constraints import (
    PLACEMENT_CATEGORIES,
    distance_bounds_m,
    is_valid_surface_stack,
    stacking_rules,
    valid_stack_parent,
    wall_distance_bounds_m,
    wall_distance_exempt,
)


def test_stacking_rules_defaults():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    assert stacking_rules("sofa") == {"on_top": False, "beneath": False}
    assert stacking_rules("rug") == {"on_top": False, "beneath": True}
    assert stacking_rules("decor") == {"on_top": True, "beneath": False}
    assert stacking_rules("lamp_desk") == {"on_top": True, "beneath": True}
    assert stacking_rules("tv") == {"on_top": True, "beneath": False}


def test_valid_stack_parent_rug_under_bed():
    assert valid_stack_parent("rug", "bed", "beneath")
    assert not valid_stack_parent("rug", "bed", "on_top")
    assert not valid_stack_parent("decor", "bed", "beneath")


def test_valid_stack_parent_decor_on_nightstand():
    assert valid_stack_parent("decor", "nightstand", "on_top")
    assert not valid_stack_parent("decor", "nightstand", "beneath")


def test_distance_bounds_symmetric():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    min_ab, max_ab = distance_bounds_m("sofa", "coffee_table", 6.0)
    min_ba, max_ba = distance_bounds_m("coffee_table", "sofa", 6.0)
    assert min_ab == min_ba
    assert max_ab == max_ba
    assert min_ab == 0.15
    assert max_ab == 0.75


def test_distance_bounds_default_uses_room_diagonal():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    min_d, max_d = distance_bounds_m("wardrobe", "fridge", 7.5)
    assert min_d == 0.0
    assert max_d == 7.5


def test_distance_bounds_explicit_pair():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    min_d, max_d = distance_bounds_m("bed", "nightstand", 5.0)
    assert min_d == 0.0
    assert max_d == 0.85


def test_is_valid_surface_stack_by_model():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    assert is_valid_surface_stack("lampRoundTable", "sideTableDrawers", mode="on_top")
    assert is_valid_surface_stack("rugRectangle", "bedDouble", mode="beneath")
    assert is_valid_surface_stack("televisionModern", "sideTable", mode="on_top")
    assert is_valid_surface_stack("televisionModern", "cabinetTelevision", mode="on_top")
    assert not is_valid_surface_stack("lampRoundFloor", "sideTable", mode="on_top")


def test_placement_categories_count():
    assert len(PLACEMENT_CATEGORIES) == 17


def test_wall_distance_exempt_categories():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    assert wall_distance_exempt("decor")
    assert wall_distance_exempt("tv")
    assert wall_distance_exempt("chair")
    assert not wall_distance_exempt("bed")


def test_wall_distance_bounds_for_bed():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    min_m, max_m = wall_distance_bounds_m("bed")
    assert min_m == 0.0
    assert max_m == 0.25


def test_wall_distance_bounds_exempt_returns_open_max():
    from colayout.placement.category_constraints import load_config
    load_config.cache_clear()
    min_m, max_m = wall_distance_bounds_m("chair")
    assert min_m == 0.0
    assert max_m is None


def test_front_clearance_config():
    from colayout.placement.category_constraints import (
        blocker_allowed_in_front_clearance,
        front_clearance_m,
        load_config,
    )

    load_config.cache_clear()
    assert front_clearance_m("dresser") == 1.5
    assert front_clearance_m("tv") == 1.0
    assert front_clearance_m("counter") == 1.5
    assert front_clearance_m("sofa") is None
    assert blocker_allowed_in_front_clearance("chair", "desk")
    assert not blocker_allowed_in_front_clearance("chair", "counter")
    assert not blocker_allowed_in_front_clearance("bookshelf", "dresser")
    assert blocker_allowed_in_front_clearance("sofa", "tv_stand")
