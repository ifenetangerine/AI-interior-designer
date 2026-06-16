"""Shared CP-SAT furniture variable bundle."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model


@dataclass
class FurnitureVars:
    item_id: str
    category: str
    model_id: str | None
    width_m: float
    length_m: float
    wc: int
    lc: int
    ox: cp_model.IntVar
    oy: cp_model.IntVar
    rot: cp_model.IntVar
    size_x: cp_model.IntVar
    size_y: cp_model.IntVar
    end_x: cp_model.IntVar
    end_y: cp_model.IntVar
    x_interval: cp_model.IntervalVar
    y_interval: cp_model.IntervalVar
    centroid_i: cp_model.IntVar
    centroid_j: cp_model.IntVar
