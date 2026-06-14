"""Apply config-driven anchor relations to a scene graph."""

from __future__ import annotations

from colayout.relations.resolver import resolve_role_constraints
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.schemas.scene import RoomSceneGraph


def apply_anchor_relation_constraints(
    graph: RoomSceneGraph,
    draft: RoomLayoutDraft,
    room: RoomSpec,
    *,
    refine_mode: bool = True,
) -> RoomSceneGraph:
    """Append role→anchor constraints from config (all soft; stacks are hard in IP)."""
    extra = resolve_role_constraints(draft, room, graph.constraints)
    if not extra:
        return graph
    constraints = list(graph.constraints) + extra
    return graph.model_copy(update={"constraints": constraints})
