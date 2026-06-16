from __future__ import annotations

from dataclasses import dataclass

from colayout.schemas.layout_draft import RoomLayoutDraft
from colayout.schemas.placement import FloorPlacementResult, RoomPlacementResult
from colayout.schemas.scene import RoomSceneGraph


@dataclass
class RoomPlacementBundle:
    placement: RoomPlacementResult
    scene_graph: RoomSceneGraph
    layout_draft: RoomLayoutDraft | None = None
    warnings: list[str] | None = None


@dataclass
class FloorPlacementBundle:
    floor: FloorPlacementResult
    scene_graphs: dict[str, RoomSceneGraph]
    layout_drafts: dict[str, RoomLayoutDraft]
