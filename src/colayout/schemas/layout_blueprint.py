"""Hierarchical layout intent: compound groups + standalone assets (Tier 1)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from colayout.schemas.scene import ObjectiveWeights


class StandaloneAssetNode(BaseModel):
    """Single Kenney asset placed independently in the room."""

    kind: Literal["standalone_asset"] = "standalone_asset"
    id: str
    model_id: str
    placement_order: int = Field(default=1, ge=1)
    center_x_m: float = Field(default=0.0, ge=0)
    center_z_m: float = Field(default=0.0, ge=0)
    orientation: int = Field(default=0, ge=0, le=3)
    composition_role: Literal["anchor", "support", "accent", "decor"] | None = None
    zone: str | None = None
    note: str | None = None


class CompoundGroupNode(BaseModel):
    """Rigid symmetric cluster expanded procedurally from a blueprint id."""

    kind: Literal["compound_group"] = "compound_group"
    id: str
    blueprint_id: str
    placement_order: int = Field(default=1, ge=1)
    center_x_m: float = Field(default=0.0, ge=0)
    center_z_m: float = Field(default=0.0, ge=0)
    orientation: int = Field(default=0, ge=0, le=3)
    zone: str | None = None
    note: str | None = None


LayoutBlueprintNode = Annotated[
    Union[StandaloneAssetNode, CompoundGroupNode],
    Field(discriminator="kind"),
]


class RoomLayoutBlueprint(BaseModel):
    """Tier-1 hierarchical room intent consumed by the blueprint expander."""

    room_id: str
    room_type: str
    nodes: list[LayoutBlueprintNode] = Field(min_length=1)
    weights: ObjectiveWeights = Field(
        default_factory=lambda: ObjectiveWeights(rel=0.2, bal=0.0, walk=0.1)
    )
