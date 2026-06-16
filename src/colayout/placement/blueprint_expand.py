"""Tier 2: expand compound blueprints into flat drafts + solver group plans."""

from __future__ import annotations

from dataclasses import dataclass

from colayout.catalog.kenney_index import footprint_for_model, placement_category
from colayout.grid.discretize import meters_to_cells
from colayout.placement.blueprint_registry import (
    CompoundBlueprint,
    get_blueprint,
    slot_category,
)
from colayout.schemas.compound import CompoundGroupPlan, CompoundMemberSpec
from colayout.schemas.layout_blueprint import (
    CompoundGroupNode,
    LayoutBlueprintNode,
    RoomLayoutBlueprint,
    StandaloneAssetNode,
)
from colayout.schemas.layout_draft import FurniturePlacementDraft, RoomLayoutDraft


@dataclass
class ExpandedLayout:
    """Flat draft plus rigid group metadata for compound-aware CP-SAT."""

    draft: RoomLayoutDraft
    compound_groups: list[CompoundGroupPlan]


def _footprint_cells(model_id: str, orientation: int, cell_m: float) -> tuple[int, int]:
    w, d = footprint_for_model(model_id)
    if orientation in (1, 3):
        w, d = d, w
    return meters_to_cells(w, cell_m), meters_to_cells(d, cell_m)


def _center_to_origin(
    cx_m: float,
    cz_m: float,
    wc: int,
    lc: int,
    cell_m: float,
) -> tuple[int, int]:
    ox = int(round((cx_m - wc * cell_m / 2) / cell_m))
    oy = int(round((cz_m - lc * cell_m / 2) / cell_m))
    return ox, oy


def _expand_blueprint_slots(
    group: CompoundGroupNode,
    blueprint: CompoundBlueprint,
    *,
    cell_m: float,
    order: int,
) -> tuple[list[FurniturePlacementDraft], CompoundGroupPlan, int]:
    """Expand one compound group; local (0,0) is group anchor in room meters."""
    placements: list[FurniturePlacementDraft] = []
    origins: list[tuple[str, int, int, int, int, int, str, str | None]] = []

    for slot in blueprint.slots:
        wc, lc = _footprint_cells(slot.model_id, slot.orientation, cell_m)
        abs_cx = group.center_x_m + slot.center_x_m
        abs_cz = group.center_z_m + slot.center_z_m
        ox, oy = _center_to_origin(abs_cx, abs_cz, wc, lc, cell_m)
        item_id = f"{group.id}__{slot.slot_id}"
        placements.append(
            FurniturePlacementDraft(
                id=item_id,
                model_id=slot.model_id,
                placement_order=order,
                center_x_m=abs_cx,
                center_z_m=abs_cz,
                orientation=slot.orientation,
                composition_role=slot.composition_role,  # type: ignore[arg-type]
                zone=group.zone,
                relative_to=group.id,
                note=group.note,
            )
        )
        origins.append(
            (
                item_id,
                ox,
                oy,
                wc,
                lc,
                slot.orientation,
                slot.model_id,
                slot_category(slot.model_id),
            )
        )
        order += 1

    min_ox = min(o for _, o, _, _, _, _, _, _ in origins)
    min_oy = min(o for _, _, o, _, _, _, _, _ in origins)
    max_ex = max(o + wc for _, o, _, wc, _, _, _, _ in origins)
    max_ey = max(o + lc for _, _, o, _, lc, _, _, _ in origins)

    members = [
        CompoundMemberSpec(
            item_id=item_id,
            local_ox_cells=ox - min_ox,
            local_oy_cells=oy - min_oy,
            width_cells=wc,
            length_cells=lc,
            orientation=orient,
            model_id=model_id,
            category=cat,
        )
        for item_id, ox, oy, wc, lc, orient, model_id, cat in origins
    ]

    plan = CompoundGroupPlan(
        group_id=group.id,
        blueprint_id=blueprint.blueprint_id,
        bbox_width_cells=max_ex - min_ox,
        bbox_length_cells=max_ey - min_oy,
        members=members,
    )
    return placements, plan, order


def expand_room_blueprint(
    blueprint: RoomLayoutBlueprint,
    *,
    cell_m: float = 0.25,
) -> ExpandedLayout:
    """Convert hierarchical intent → flat draft + compound group plans."""
    placements: list[FurniturePlacementDraft] = []
    compound_groups: list[CompoundGroupPlan] = []
    order = 1

    for node in blueprint.nodes:
        if isinstance(node, StandaloneAssetNode):
            placements.append(
                FurniturePlacementDraft(
                    id=node.id,
                    model_id=node.model_id,
                    placement_order=order,
                    center_x_m=node.center_x_m,
                    center_z_m=node.center_z_m,
                    orientation=node.orientation,
                    composition_role=node.composition_role,
                    zone=node.zone,
                    note=node.note,
                )
            )
            order += 1
        elif isinstance(node, CompoundGroupNode):
            bp = get_blueprint(node.blueprint_id)
            group_placements, plan, order = _expand_blueprint_slots(
                node, bp, cell_m=cell_m, order=order
            )
            placements.extend(group_placements)
            compound_groups.append(plan)

    draft = RoomLayoutDraft(
        room_id=blueprint.room_id,
        room_type=blueprint.room_type,
        placements=placements,
        weights=blueprint.weights,
    )
    return ExpandedLayout(draft=draft, compound_groups=compound_groups)


def parse_blueprint_nodes(raw_nodes: list[dict]) -> list[LayoutBlueprintNode]:
    """Parse Tier-1 JSON node list (discriminator: kind)."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(list[LayoutBlueprintNode])
    return adapter.validate_python(raw_nodes)


def room_blueprint_from_dict(data: dict) -> RoomLayoutBlueprint:
    payload = dict(data)
    if "nodes" in payload:
        payload["nodes"] = parse_blueprint_nodes(payload["nodes"])
    return RoomLayoutBlueprint.model_validate(payload)
