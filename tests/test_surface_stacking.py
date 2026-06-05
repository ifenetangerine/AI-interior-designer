"""Surface stacking: lamps on tables, rugs under coffee table."""

from colayout.assets.kenney import match_kenney_assets, load_kenney_catalog
from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import draft_to_hints, draft_to_scene_graph
from colayout.llm.provider import MockLLMProvider
from colayout.pipeline.place import place_room_with_graph
from colayout.schemas.floor import RoomSpec
from colayout.schemas.scene import ConstraintType


def test_bedroom_refine_keeps_lamp_on_nightstand():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    lamp = next(p for p in draft.placements if "lamp" in p.model_id.lower())
    ns = next(p for p in draft.placements if p.id.startswith("nightstand"))
    assert abs(lamp.center_x_m - ns.center_x_m) < 0.15
    grid = discretize_room(room, 0.25)
    graph = draft_to_scene_graph(draft, room)
    stack_types = {c.type for c in graph.constraints}
    assert ConstraintType.ON_TOP_OF in stack_types
    result = solve_room_placement(
        graph,
        grid,
        SolveConfig(hints=draft_to_hints(draft, grid), soft_constraints=True, time_limit_s=15),
    )
    assert result is not None
    by_id = {f.id: f for f in result.furniture}
    assert lamp.id in by_id and ns.id in by_id
    assert by_id[lamp.id].stack_parent_id == ns.id
    assert by_id[lamp.id].origin_i == by_id[ns.id].origin_i
    assert by_id[lamp.id].origin_j == by_id[ns.id].origin_j


def test_stacked_lamp_has_vertical_position():
    room = RoomSpec(id="bed", type="bedroom", width_m=4.0, length_m=3.5)
    bundle = place_room_with_graph(room, MockLLMProvider(), 0.25)
    assert bundle is not None
    placements = match_kenney_assets(bundle.placement, load_kenney_catalog())
    elevated = [p for p in placements if p.position_m[1] > 0.05]
    assert len(elevated) >= 1


def test_living_rug_under_coffee_table():
    room = RoomSpec(id="lr", type="living_room", width_m=4.0, length_m=3.5)
    draft = MockLLMProvider().generate_layout_draft(room)
    graph = draft_to_scene_graph(draft, room)
    under = [c for c in graph.constraints if c.type == ConstraintType.UNDER]
    assert len(under) >= 1
