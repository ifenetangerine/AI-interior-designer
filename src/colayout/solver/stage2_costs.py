"""Differentiable aesthetic cost terms for Stage-2 continuous refinement.

Each cost is a smooth function of continuous positions
``(x, z, theta_deg)`` per free furniture item.  See ``domain_transform`` for
the coordinate conventions used by the optimization vector ``X``.

Energy assembly (in ``stage2_refiner``)::

    E = w_overlap * C_overlap
      + w_sightline * C_sightline
      + w_wall * C_wall
      + w_anchor * C_anchor
"""

from __future__ import annotations

import math

from colayout.solver.hybrid_types import FurniturePosition, HybridFurnitureItem


def proxy_radius(item: HybridFurnitureItem) -> float:
    """Circumscribed circle radius for smooth overlap proxy."""
    w, d = item.dimensions.width_x, item.dimensions.depth_z
    return 0.5 * math.hypot(w, d)


def forward_vector(theta_rad: float) -> tuple[float, float]:
    return math.cos(theta_rad), math.sin(theta_rad)


def nearest_wall_info(
    x: float,
    z: float,
    width_m: float,
    length_m: float,
) -> tuple[str, float, tuple[float, float]]:
    dists = {
        "west": x,
        "east": width_m - x,
        "south": z,
        "north": length_m - z,
    }
    wall = min(dists, key=dists.get)
    normal = {
        "west": (1.0, 0.0),
        "east": (-1.0, 0.0),
        "south": (0.0, 1.0),
        "north": (0.0, -1.0),
    }[wall]
    return wall, dists[wall], normal


def overlap_cost(
    items: list[HybridFurnitureItem],
    positions: dict[str, FurniturePosition],
) -> float:
    """Squared hinge loss on proxy-circle overlap: max(0, R_i + R_j - d)^2."""
    cost = 0.0
    n = len(items)
    radii = [proxy_radius(it) for it in items]
    for i in range(n):
        pi = positions[items[i].id]
        for j in range(i + 1, n):
            pj = positions[items[j].id]
            dist = math.hypot(pi.x - pj.x, pi.z - pj.z)
            gap = radii[i] + radii[j] - dist
            if gap > 0:
                cost += gap * gap
    return cost


def sightline_cost(
    items: list[HybridFurnitureItem],
    positions: dict[str, FurniturePosition],
) -> float:
    """Conversational / focal sightline: 1 - dot(forward, to_target_hat)."""
    by_id = {it.id: it for it in items}
    cost = 0.0
    for item in items:
        if not item.focal_target_id:
            continue
        target_item = by_id.get(item.focal_target_id)
        if not target_item:
            continue
        p = positions[item.id]
        t = positions[target_item.id]
        dx = t.x - p.x
        dz = t.z - p.z
        dist = math.hypot(dx, dz)
        if dist < 1e-6:
            continue
        ux, uz = dx / dist, dz / dist
        fx, fz = forward_vector(math.radians(p.theta_deg))
        cost += max(0.0, 1.0 - (fx * ux + fz * uz))
    return cost


def wall_anchor_cost(
    items: list[HybridFurnitureItem],
    positions: dict[str, FurniturePosition],
    width_m: float,
    length_m: float,
) -> float:
    """Wall anchoring: squared distance to nearest wall + back-normal misalignment."""
    cost = 0.0
    for item in items:
        if not item.is_wall_anchor:
            continue
        if (item.category or item.item_type) == "bed":
            continue
        p = positions[item.id]
        _wall, dist, normal = nearest_wall_info(p.x, p.z, width_m, length_m)
        cost += dist * dist
        fx, fz = forward_vector(math.radians(p.theta_deg))
        back_x, back_z = -fx, -fz
        align = back_x * normal[0] + back_z * normal[1]
        cost += max(0.0, 1.0 - align) ** 2
    return cost


def anchor_cost(
    items: list[HybridFurnitureItem],
    positions: dict[str, FurniturePosition],
    stage1: dict[str, FurniturePosition],
) -> float:
    """Soft penalty keeping items near verified Stage-1 positions."""
    cost = 0.0
    for item in items:
        p = positions[item.id]
        s = stage1[item.id]
        dx = p.x - s.x
        dz = p.z - s.z
        cost += dx * dx + dz * dz
        d_theta = math.radians((p.theta_deg - s.theta_deg + 180) % 360 - 180)
        cost += d_theta * d_theta
    return cost


def total_energy(
    items: list[HybridFurnitureItem],
    positions: dict[str, FurniturePosition],
    stage1: dict[str, FurniturePosition],
    width_m: float,
    length_m: float,
    *,
    w_overlap: float,
    w_sightline: float,
    w_wall: float,
    w_anchor: float,
) -> float:
    return (
        w_overlap * overlap_cost(items, positions)
        + w_sightline * sightline_cost(items, positions)
        + w_wall * wall_anchor_cost(items, positions, width_m, length_m)
        + w_anchor * anchor_cost(items, positions, stage1)
    )
