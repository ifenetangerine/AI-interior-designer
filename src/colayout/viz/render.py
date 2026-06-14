from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as patches

from colayout.schemas.placement import RoomPlacementResult

COLORS = {
    "bed": "#6b8e9f",
    "wardrobe": "#8b7355",
    "desk": "#7a9e7e",
    "chair": "#c4a35a",
    "sofa": "#5c7a99",
    "tv_stand": "#4a4a4a",
    "tv": "#2a2a2a",
    "coffee_table": "#a67c52",
    "counter": "#9e9e9e",
    "fridge": "#b0c4de",
    "dining_table": "#8fbc8f",
}


def render_room(result: RoomPlacementResult, out_path: Path) -> None:
    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    w, l = result.grid_w, result.grid_l
    cell = result.modulor_cell_m

    ax.set_xlim(0, w * cell)
    ax.set_ylim(0, l * cell)
    ax.set_aspect("equal")
    ax.set_title(f"{result.room_id} ({result.room_type})")
    ax.set_xlabel("m")
    ax.set_ylabel("m")

    room_rect = patches.Rectangle(
        (0, 0), w * cell, l * cell, linewidth=2, edgecolor="black", facecolor="#f5f5f0"
    )
    ax.add_patch(room_rect)

    for f in result.furniture:
        color = COLORS.get(f.category, "#cccccc")
        x = f.origin_i * cell
        y = f.origin_j * cell
        rect = patches.Rectangle(
            (x, y),
            f.width_cells * cell,
            f.length_cells * cell,
            linewidth=1,
            edgecolor="black",
            facecolor=color,
            alpha=0.85,
        )
        ax.add_patch(rect)
        cx = x + f.width_cells * cell / 2
        cy = y + f.length_cells * cell / 2
        ax.text(cx, cy, f.id, ha="center", va="center", fontsize=8)

        # Facing arrow from mesh-front orientation (skip rugs/decor).
        if f.category not in ("decor",):
            try:
                from colayout.assets.kenney import load_kenney_catalog
                from colayout.placement.orient import _world_front

                fx, fz = _world_front(
                    f.model_id, f.category, f.orientation, load_kenney_catalog()
                )
                alen = min(f.width_cells, f.length_cells) * cell * 0.4
                ax.arrow(
                    cx,
                    cy,
                    fx * alen,
                    fz * alen,
                    head_width=alen * 0.35,
                    head_length=alen * 0.3,
                    fc="#d62728",
                    ec="#d62728",
                    length_includes_head=True,
                )
            except Exception:
                pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
