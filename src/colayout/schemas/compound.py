"""Compound group metadata for rigid CP-SAT bounding-box placement."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompoundMemberSpec(BaseModel):
    """Child asset offset from group bbox origin (grid cells, fixed orientation)."""

    item_id: str
    local_ox_cells: int
    local_oy_cells: int
    width_cells: int
    length_cells: int
    orientation: int = Field(default=0, ge=0, le=3)
    model_id: str
    category: str | None = None


class CompoundGroupPlan(BaseModel):
    """Rigid group: master cluster_x/z; children use fixed local offsets."""

    group_id: str
    blueprint_id: str
    bbox_width_cells: int = Field(gt=0)
    bbox_length_cells: int = Field(gt=0)
    members: list[CompoundMemberSpec] = Field(min_length=1)

    @property
    def member_ids(self) -> list[str]:
        return [m.item_id for m in self.members]
