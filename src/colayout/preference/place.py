"""Place a frozen golden draft with tunable relational θ."""

from __future__ import annotations

from dataclasses import dataclass

from colayout.grid.discretize import discretize_room
from colayout.ip.solver import SolveConfig, solve_room_placement
from colayout.llm.draft_to_hints import (
    draft_to_hints,
    draft_to_scene_graph,
    placement_result_from_draft,
)
from colayout.placement.orient import apply_facing_orientations
from colayout.preference.features import extract_features
from colayout.preference.theta import apply_theta, clamp_theta
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.schemas.placement import RoomPlacementResult
from colayout.schemas.scene import RoomSceneGraph


@dataclass
class ThetaPlacementResult:
    placement: RoomPlacementResult
    scene_graph: RoomSceneGraph
    features: dict[str, float]
    theta: dict[str, float]


def place_from_draft_with_theta(
    room: RoomSpec,
    draft: RoomLayoutDraft,
    theta: dict[str, float],
    *,
    modulor_cell_m: float = 0.25,
    hint_scale: float = 0.0,
    time_limit_s: float = 15.0,
) -> ThetaPlacementResult | None:
    """IP-refine a frozen draft; relational θ drives soft penalties."""
    theta = clamp_theta(theta, room.type)
    grid = discretize_room(room, modulor_cell_m)
    graph = draft_to_scene_graph(draft, room, refine_mode=True)
    graph = apply_theta(graph, theta)
    hints = draft_to_hints(draft, grid)

    placement = solve_room_placement(
        graph,
        grid,
        SolveConfig(
            hints=hints,
            soft_constraints=True,
            hint_scale=hint_scale,
            time_limit_s=time_limit_s,
        ),
    )
    if placement is None:
        placement = apply_facing_orientations(
            placement_result_from_draft(draft, grid), graph
        )
    else:
        placement = apply_facing_orientations(placement, graph)

    features = extract_features(placement, graph, room)
    return ThetaPlacementResult(
        placement=placement,
        scene_graph=graph,
        features=features,
        theta=theta,
    )
