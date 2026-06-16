"""Procedural compound blueprints with catalog-accurate symmetric local offsets."""

from __future__ import annotations

from dataclasses import dataclass

from colayout.catalog.kenney_index import footprint_for_model, placement_category


@dataclass(frozen=True)
class BlueprintSlot:
    """One child asset in group-local coordinates (meters, center-relative)."""

    slot_id: str
    model_id: str
    center_x_m: float
    center_z_m: float
    orientation: int = 0
    composition_role: str | None = None


@dataclass(frozen=True)
class CompoundBlueprint:
    blueprint_id: str
    slots: tuple[BlueprintSlot, ...]


def _half(model_id: str) -> tuple[float, float]:
    w, d = footprint_for_model(model_id)
    return w / 2.0, d / 2.0


def _symmetric_lounge() -> CompoundBlueprint:
    """Coffee table at origin; sofa north (+z); flank chairs east/west."""
    coffee = "tableCoffee"
    sofa = "loungeSofa"
    chair = "loungeChair"
    cw, cd = _half(coffee)
    sw, sd = _half(sofa)
    chw, _ = _half(chair)
    sofa_gap = 0.35
    flank_gap = 0.40
    z_sofa = cd + sofa_gap + sd
    x_chair = cw + flank_gap + chw
    return CompoundBlueprint(
        blueprint_id="symmetric_lounge",
        slots=(
            BlueprintSlot("coffee_table", coffee, 0.0, 0.0, 0, "anchor"),
            BlueprintSlot("sofa", sofa, 0.0, z_sofa, 0, "support"),
            BlueprintSlot("chair_l", chair, -x_chair, 0.0, 1, "accent"),
            BlueprintSlot("chair_r", chair, x_chair, 0.0, 3, "accent"),
        ),
    )


def _bedside_cluster() -> CompoundBlueprint:
    """Bed at origin; nightstands symmetrically flanking headboard (+z)."""
    bed = "bedDouble"
    ns = "sideTable"
    bw, bd = _half(bed)
    nsw, nsd = _half(ns)
    gap = 0.05
    x_ns = bw + gap + nsw
    z_ns = bd - nsd
    return CompoundBlueprint(
        blueprint_id="bedside_cluster",
        slots=(
            BlueprintSlot("bed", bed, 0.0, 0.0, 1, "anchor"),
            BlueprintSlot("nightstand_l", ns, -x_ns, z_ns, 1, "support"),
            BlueprintSlot("nightstand_r", ns, x_ns, z_ns, 1, "support"),
        ),
    )


def _desk_cluster() -> CompoundBlueprint:
    """Desk at origin; chair centered in front (+x, toward room)."""
    desk = "desk"
    chair = "chairDesk"
    dw, dd = _half(desk)
    cw, cd = _half(chair)
    gap = 0.25
    x_chair = dw + gap + cw
    return CompoundBlueprint(
        blueprint_id="desk_cluster",
        slots=(
            BlueprintSlot("desk", desk, 0.0, 0.0, 0, "anchor"),
            BlueprintSlot("chair", chair, x_chair, 0.0, 0, "support"),
        ),
    )


def _dining_set(*, seats: int = 4) -> CompoundBlueprint:
    """Dining table at origin with symmetric chair ring."""
    table = "table"
    chair = "chair"
    tw, td = _half(table)
    cw, cd = _half(chair)
    gap = 0.30
    slots: list[BlueprintSlot] = [
        BlueprintSlot("table", table, 0.0, 0.0, 0, "anchor"),
    ]
    if seats >= 1:
        slots.append(
            BlueprintSlot("chair_n", chair, 0.0, -(td + gap + cd), 0, "support")
        )
    if seats >= 2:
        slots.append(
            BlueprintSlot("chair_s", chair, 0.0, td + gap + cd, 2, "support")
        )
    if seats >= 3:
        slots.append(
            BlueprintSlot("chair_w", chair, -(tw + gap + cw), 0.0, 1, "support")
        )
    if seats >= 4:
        slots.append(
            BlueprintSlot("chair_e", chair, tw + gap + cw, 0.0, 3, "support")
        )
    return CompoundBlueprint(blueprint_id="dining_set", slots=tuple(slots))


def _tv_viewing_wall() -> CompoundBlueprint:
    """TV stand north; coffee center; sofa south — aligned viewing axis."""
    tv = "sideTable"
    sofa = "loungeSofa"
    coffee = "tableCoffee"
    _, td = _half(tv)
    sw, sd = _half(sofa)
    cw, cd = _half(coffee)
    gap_tv = 0.50
    gap_sofa = 0.35
    z_sofa = -(sd + gap_sofa + cd)
    z_coffee = z_sofa + sd + gap_sofa + cd
    z_tv = z_coffee + cd + gap_tv + td
    return CompoundBlueprint(
        blueprint_id="tv_viewing_wall",
        slots=(
            BlueprintSlot("sofa", sofa, 0.0, z_sofa, 1, "support"),
            BlueprintSlot("coffee_table", coffee, 0.0, z_coffee, 0, "support"),
            BlueprintSlot("tv_stand", tv, 0.0, z_tv, 1, "anchor"),
        ),
    )


_BLUEPRINTS: dict[str, CompoundBlueprint] = {}


def _register(bp: CompoundBlueprint) -> CompoundBlueprint:
    _BLUEPRINTS[bp.blueprint_id] = bp
    return bp


_register(_symmetric_lounge())
_register(_bedside_cluster())
_register(_desk_cluster())
_register(_dining_set())
_register(_tv_viewing_wall())


def get_blueprint(blueprint_id: str) -> CompoundBlueprint:
    if blueprint_id not in _BLUEPRINTS:
        raise KeyError(
            f"Unknown compound blueprint '{blueprint_id}'; "
            f"known: {sorted(_BLUEPRINTS)}"
        )
    return _BLUEPRINTS[blueprint_id]


def list_blueprint_ids() -> list[str]:
    return sorted(_BLUEPRINTS)


def slot_category(model_id: str) -> str:
    return placement_category(model_id)
