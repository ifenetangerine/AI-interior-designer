from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from colayout.schemas.architecture import RoomArchitecture


class ConstraintType(str, Enum):
    AGAINST_WALL = "against_wall"
    ALIGNMENT = "alignment"
    FACING = "facing"
    ADJACENT = "adjacent"
    RELATIVE_POSITION = "relative_position"
    FLANK = "flank"
    IN_FRONT_OF = "in_front_of"
    SEATS_AROUND = "seats_around"
    ADJACENT_CHAIN = "adjacent_chain"
    ON_TOP_OF = "on_top_of"
    UNDER = "under"
    CENTERED_UNDER = "centered_under"
    SYMMETRIC_PAIR = "symmetric_pair"


class FurnitureItem(BaseModel):
    id: str
    model_id: str | None = None
    category: str | None = None
    width_m: float | None = Field(default=None, gt=0)
    length_m: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_model_or_category(self) -> "FurnitureItem":
        if not self.model_id and not self.category:
            raise ValueError(
                f"furniture '{self.id}' requires model_id or category"
            )
        return self


class FurnitureConstraint(BaseModel):
    type: ConstraintType
    furniture: str | None = None
    furniture_a: str | None = None
    furniture_b: str | None = None
    furniture_ids: list[str] = Field(default_factory=list)
    wall: Literal["north", "south", "east", "west", "any"] | None = None
    side: Literal["left", "right"] | None = None
    axis: Literal["i", "j"] | None = None
    offset_i: float = 0.0
    offset_j: float = 0.0
    distance_m: float = 0.2
    min_seats: int = 2
    hard: bool = False
    weight: float = 8.0
    rule_key: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "FurnitureConstraint":
        if self.type == ConstraintType.AGAINST_WALL:
            if not self.furniture:
                raise ValueError("against_wall requires furniture")
        elif self.type == ConstraintType.SEATS_AROUND:
            if not self.furniture:
                raise ValueError("seats_around requires furniture (table id)")
        elif self.type == ConstraintType.ADJACENT_CHAIN:
            if len(self.furniture_ids) < 2:
                raise ValueError("adjacent_chain requires at least 2 furniture_ids")
            if not self.wall or self.wall == "any":
                raise ValueError("adjacent_chain requires a specific wall")
        elif self.type == ConstraintType.FLANK:
            if not self.furniture_a or not self.furniture_b or not self.side:
                raise ValueError("flank requires furniture_a, furniture_b, and side")
        elif self.type == ConstraintType.SYMMETRIC_PAIR:
            if not self.furniture or not self.furniture_a or not self.furniture_b:
                raise ValueError(
                    "symmetric_pair requires furniture (anchor), furniture_a, furniture_b"
                )
            if not self.axis:
                raise ValueError("symmetric_pair requires axis i or j")
        elif self.type in (
            ConstraintType.ALIGNMENT,
            ConstraintType.FACING,
            ConstraintType.ADJACENT,
            ConstraintType.RELATIVE_POSITION,
            ConstraintType.IN_FRONT_OF,
            ConstraintType.ON_TOP_OF,
            ConstraintType.UNDER,
            ConstraintType.CENTERED_UNDER,
        ):
            if not self.furniture_a or not self.furniture_b:
                raise ValueError(f"{self.type} requires furniture_a and furniture_b")
        return self


class ObjectiveWeights(BaseModel):
    rel: float = 1.0
    bal: float = 0.0
    walk: float = 0.7
    balance: float = 0.3
    proportion: float = 0.2
    rhythm: float = 0.1


class ThetaMetrics(BaseModel):
    """Tunable layout metric targets applied during IP refine."""

    adjacent_gap_m: float = 0.0
    symmetry_strength: float = 12.0
    on_surface_strength: float = 10.0
    orphan_radius_m: float = 2.0
    orphan_weight: float = 4.0
    door_clearance_min_m: float = 0.9
    chair_desk_dist_m: float | None = None
    sofa_coffee_dist_m: float | None = None
    sofa_tv_dist_m: float | None = None
    bar_stool_dist_m: float | None = None
    wall_inset_sleep_m: float | None = None
    wall_inset_seating_m: float | None = None
    wall_inset_storage_m: float | None = None


class RoomSceneGraph(BaseModel):
    room_id: str
    room_type: str
    furniture: list[FurnitureItem] = Field(min_length=1)
    constraints: list[FurnitureConstraint] = Field(default_factory=list)
    weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)
    architecture: RoomArchitecture | None = None
    theta_metrics: ThetaMetrics | None = None
