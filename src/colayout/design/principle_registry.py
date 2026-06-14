"""Single source of truth for interior design principles → LLM, validation, IP."""

from __future__ import annotations

from dataclasses import dataclass

from colayout.schemas.architecture import (
    RoomArchitecture,
    architecture_prompt_lines,
    resolve_architecture,
)
from colayout.schemas.floor import RoomSpec

COFFEE_SOFA_MIN_M = 0.35
COFFEE_SOFA_MAX_M = 0.45
BALANCE_TOLERANCE = 0.15


@dataclass(frozen=True)
class PrincipleEntry:
    name: str
    llm_guidance: str


PRINCIPLES: tuple[PrincipleEntry, ...] = (
    PrincipleEntry(
        "Structure",
        "Anchor first (placement_order 1), then support pieces, then accents and decor. "
        "Tag each piece with composition_role and zone.",
    ),
    PrincipleEntry(
        "Emphasis",
        "Orient seating toward the TV anchor. Place the TV on the viewing wall.",
    ),
    PrincipleEntry(
        "Balance",
        "Distribute visual weight left/right of room midline; symmetry optional but mass should not cluster on one side.",
    ),
    PrincipleEntry(
        "Proportion",
        f"Coffee table {int(COFFEE_SOFA_MIN_M*100)}–{int(COFFEE_SOFA_MAX_M*100)} cm from sofa front. "
        "Scale accent pieces to anchor size.",
    ),
    PrincipleEntry(
        "Rhythm",
        "Repeat paired elements (nightstands, lamps) with even spacing along walls.",
    ),
    PrincipleEntry(
        "Harmony",
        "Reuse consistent materials/forms; avoid mixing unrelated styles unless preferences request eclectic.",
    ),
    PrincipleEntry(
        "Unity",
        "Align major pieces to room axes; zones should read as one coherent composition.",
    ),
)


def principles_guidance_block() -> str:
    lines = ["## Classical design principles (apply to every layout)"]
    for p in PRINCIPLES:
        lines.append(f"- **{p.name}**: {p.llm_guidance}")
    return "\n".join(lines)


def placement_guidance_for_room(room: RoomSpec) -> str:
    """LLM placement instructions derived from principles + room context."""
    from colayout.llm.room_program import (
        anchor_placement_guidance,
        density_tier,
        required_furniture_prompt,
        room_area_m2,
        staging_prompt,
    )

    arch = resolve_architecture(
        room.type, room.width_m, room.length_m, room.architecture
    )
    tier = density_tier(room_area_m2(room))
    w, l = room.width_m, room.length_m
    lines = [
        principles_guidance_block(),
        anchor_placement_guidance(room),
        required_furniture_prompt(room.type),
        "Surface stacking:",
        "- Table lamps: set on_surface_of to nightstand/side_table/coffee_table id; same center as surface.",
        "- Rugs only: on_surface_of coffee_table or sofa (under seating zone; same center as parent).",
        "- Never on_surface_of for coffee_table, side_table, dining_table, or desk — floor furniture; use relative_to and distinct centers.",
        "Wall anchoring:",
        "- Storage and built-ins: back against a wall.",
        f"- Room size: {w:.1f} m × {l:.1f} m (tier {tier}).",
    ]
    staging = staging_prompt(room.type, tier)
    if staging:
        lines.append(staging)
    lines.extend(architecture_prompt_lines(arch, w, l))
    if room.type == "bedroom":
        lines.append(
            "- Bed headboard west. Nightstands flank bed. Desk east; chair at desk."
        )
    elif room.type == "living_room":
        lines.append(
            "- Sofa facing TV anchor; coffee table between; fill seating zone at standard tier."
        )
    elif room.type == "kitchen":
        lines.append(
            "- Dining table floats. Sink + counter run on north wall."
        )
    return "\n".join(lines)
