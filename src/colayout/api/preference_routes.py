"""Golden layouts and preference training API."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from colayout.assets.kenney import load_kenney_catalog, match_kenney_assets
from colayout.llm.validate_placement import (
    is_blocking_placement_error,
    validate_golden_layout_draft,
    validate_layout_draft,
)
from colayout.preference.llm_designs import (
    draft_from_cached,
    list_cached_llm_designs,
    load_cached_llm_design,
    pick_random_design_id,
    room_from_design,
)
from colayout.preference.place import place_from_draft_with_theta
from colayout.preference.store import (
    delete_golden_layout,
    list_golden_layouts,
    load_golden_layout,
    save_golden_layout,
)
from colayout.preference.trainer import PreferenceTrainer
from colayout.schemas.architecture import RoomArchitecture
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft

router = APIRouter(prefix="/api")

ROOT = Path(__file__).resolve().parents[3]
RELATIONS_PATH = ROOT / "config" / "furniture_anchor_relations.yaml"
LEARNED_RELATIONS_PATH = ROOT / "config" / "furniture_anchor_relations.learned.yaml"
THETA_LEARNED_PATH = ROOT / "config" / "preference_theta.learned.yaml"


class GoldenLayoutSaveRequest(BaseModel):
    id: str
    label: str = ""
    room_type: str
    width_m: float = Field(gt=0)
    length_m: float = Field(gt=0)
    architecture: RoomArchitecture | None = None
    draft: dict
    few_shot: bool = True


class GoldenValidateRequest(BaseModel):
    room_type: str
    width_m: float = Field(gt=0)
    length_m: float = Field(gt=0)
    draft: dict


class PreferencePairRequest(BaseModel):
    room_type: str | None = None
    design_id: str | None = None
    modulor_cell_m: float = Field(default=0.25, gt=0)
    time_limit_s: float = Field(default=8.0, gt=0)


class PreferenceCompareRequest(BaseModel):
    design_id: str
    theta_A: dict[str, float]
    theta_B: dict[str, float]
    winner: str
    features_A: dict[str, float]
    features_B: dict[str, float]


class ExportYamlRequest(BaseModel):
    room_type: str


class GoldenPreviewRequest(BaseModel):
    room_type: str
    width_m: float = Field(gt=0)
    length_m: float = Field(gt=0)
    architecture: RoomArchitecture | None = None
    draft: dict
    modulor_cell_m: float = Field(default=0.25, gt=0)


def _golden_to_room(record: dict) -> RoomSpec:
    arch = record.get("architecture")
    return RoomSpec(
        id=record.get("id", "golden"),
        type=record["room_type"],
        width_m=float(record["width_m"]),
        length_m=float(record["length_m"]),
        architecture=RoomArchitecture.model_validate(arch) if arch else None,
    )


def _solve_variant(
    cached_llm: dict,
    theta: dict[str, float],
    *,
    modulor_cell_m: float,
    time_limit_s: float,
) -> dict:
    room = room_from_design(cached_llm)
    draft = draft_from_cached(cached_llm)
    result = place_from_draft_with_theta(
        room,
        draft,
        theta,
        modulor_cell_m=modulor_cell_m,
        hint_scale=0.0,
        time_limit_s=time_limit_s,
    )
    if result is None:
        raise HTTPException(status_code=422, detail="Placement solve failed")
    catalog = load_kenney_catalog()
    placements = match_kenney_assets(result.placement, catalog)
    return {
        "theta": result.theta,
        "features": result.features,
        "layout": result.placement.model_dump(),
        "placements": [p.model_dump() for p in placements],
    }


@router.get("/golden-layouts")
def golden_list(room_type: str | None = None) -> dict:
    from colayout.preference.store import GOLDEN_DIR, ROOT

    try:
        storage_dir = str(GOLDEN_DIR.relative_to(ROOT))
    except ValueError:
        storage_dir = str(GOLDEN_DIR)
    return {
        "layouts": list_golden_layouts(room_type),
        "storage_dir": storage_dir,
    }


@router.get("/golden-layouts/{golden_id}")
def golden_get(golden_id: str) -> dict:
    try:
        return load_golden_layout(golden_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/golden-layouts")
def golden_save(req: GoldenLayoutSaveRequest) -> dict:
    gid = re.sub(r"[^a-zA-Z0-9_-]+", "_", req.id.strip()) or "golden"
    draft = RoomLayoutDraft.model_validate(
        {**req.draft, "room_id": gid, "room_type": req.room_type}
    )
    record = save_golden_layout(
        gid,
        label=req.label or gid,
        room_type=req.room_type,
        width_m=req.width_m,
        length_m=req.length_m,
        draft=draft,
        architecture=req.architecture,
        few_shot=req.few_shot,
    )
    return record


@router.delete("/golden-layouts/{golden_id}")
def golden_delete(golden_id: str) -> dict:
    try:
        load_golden_layout(golden_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    delete_golden_layout(golden_id)
    return {"status": "deleted", "id": golden_id}


@router.post("/golden-layouts/preview")
def golden_preview(req: GoldenPreviewRequest) -> dict:
    from colayout.grid.discretize import discretize_room
    from colayout.llm.draft_to_hints import (
        auto_link_overlapping_stacks,
        placement_result_from_draft,
    )

    room = RoomSpec(
        id="preview",
        type=req.room_type,
        width_m=req.width_m,
        length_m=req.length_m,
        architecture=req.architecture,
    )
    draft = RoomLayoutDraft.model_validate(
        {**req.draft, "room_id": "preview", "room_type": req.room_type}
    )
    linked = auto_link_overlapping_stacks(list(draft.placements))
    draft = draft.model_copy(update={"placements": linked})
    grid = discretize_room(room, req.modulor_cell_m)
    # Golden editor: keep draft orientations; do not auto-face (overrides manual rotate).
    # Golden editor uses continuous drag coordinates; do not snap to grid cells.
    placement = placement_result_from_draft(draft, grid, preserve_centers=True)
    catalog = load_kenney_catalog()
    placements = match_kenney_assets(placement, catalog)
    return {
        "placements": [p.model_dump() for p in placements],
        "layout": placement.model_dump(),
        "draft": draft.model_dump(),
    }


@router.post("/golden-layouts/validate")
def golden_validate(req: GoldenValidateRequest) -> dict:
    room = RoomSpec(
        id="validate",
        type=req.room_type,
        width_m=req.width_m,
        length_m=req.length_m,
    )
    draft = RoomLayoutDraft.model_validate(
        {**req.draft, "room_id": "validate", "room_type": req.room_type}
    )
    sanitized, errors = validate_golden_layout_draft(draft, room)
    blocking = [e for e in errors if is_blocking_placement_error(e)]
    return {
        "valid": not blocking,
        "errors": errors,
        "blocking_errors": blocking,
        "draft": sanitized.model_dump(),
    }


@router.get("/preference/theta-schema")
def preference_theta_schema(room_type: str) -> dict:
    trainer = PreferenceTrainer(room_type)
    return {"room_type": room_type, "params": trainer.schema_payload()}


@router.get("/preference/state")
def preference_state(room_type: str) -> dict:
    trainer = PreferenceTrainer(room_type)
    state = trainer.load_state()
    return {
        "room_type": room_type,
        "theta_current": state.theta_current,
        "comparison_count": state.comparison_count,
        "phase": state.phase,
        "top_deltas": trainer.top_theta_deltas(5),
    }


@router.get("/preference/llm-designs")
def preference_llm_designs_list(room_type: str | None = None) -> dict:
    return {"designs": list_cached_llm_designs(room_type)}


@router.get("/preference/llm-designs/{design_id}")
def preference_llm_design_get(design_id: str) -> dict:
    cached = load_cached_llm_design(design_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="No cached LLM design")
    return cached


def _resolve_cached_design(
    *,
    room_type: str | None,
    design_id: str | None,
) -> tuple[str, dict]:
    if design_id:
        cached = load_cached_llm_design(design_id)
        if cached is None:
            raise HTTPException(
                status_code=404,
                detail=f"No cached LLM design: {design_id}. "
                "Run scripts/cache_llm_designs.py first.",
            )
        return design_id, cached

    if not room_type:
        raise HTTPException(
            status_code=400,
            detail="room_type or design_id is required",
        )
    picked = pick_random_design_id(room_type)
    if picked is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached LLM designs for {room_type}. "
            "Run scripts/cache_llm_designs.py first.",
        )
    cached = load_cached_llm_design(picked)
    assert cached is not None
    return picked, cached


@router.post("/preference/pair")
def preference_pair(req: PreferencePairRequest) -> dict:
    design_id, cached_llm = _resolve_cached_design(
        room_type=req.room_type,
        design_id=req.design_id,
    )

    room_type = cached_llm["room_type"]
    trainer = PreferenceTrainer(room_type)
    theta_a, theta_b = trainer.sample_pair()

    solve_kw = {
        "modulor_cell_m": req.modulor_cell_m,
        "time_limit_s": req.time_limit_s,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_solve_variant, cached_llm, theta_a, **solve_kw)
        fut_b = pool.submit(_solve_variant, cached_llm, theta_b, **solve_kw)
        variant_a = fut_a.result()
        variant_b = fut_b.result()
    state = trainer.load_state()
    return {
        "design_id": design_id,
        "room_type": room_type,
        "width_m": cached_llm.get("width_m"),
        "length_m": cached_llm.get("length_m"),
        "theta_A": variant_a["theta"],
        "theta_B": variant_b["theta"],
        "features_A": variant_a["features"],
        "features_B": variant_b["features"],
        "layout_A": variant_a["layout"],
        "layout_B": variant_b["layout"],
        "placements_A": variant_a["placements"],
        "placements_B": variant_b["placements"],
        "comparison_count": state.comparison_count,
        "phase": state.phase,
    }


@router.post("/preference/compare")
def preference_compare(req: PreferenceCompareRequest) -> dict:
    cached = load_cached_llm_design(req.design_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="No cached LLM design")

    room_type = cached["room_type"]
    if req.winner not in ("A", "B", "tie"):
        raise HTTPException(status_code=400, detail="winner must be A, B, or tie")

    trainer = PreferenceTrainer(room_type)
    state = trainer.record_comparison(
        design_id=req.design_id,
        theta_a=req.theta_A,
        theta_b=req.theta_B,
        winner=req.winner,
        features_a=req.features_A,
        features_b=req.features_B,
    )
    return {
        "room_type": room_type,
        "design_id": req.design_id,
        "theta_current": state.theta_current,
        "comparison_count": state.comparison_count,
        "phase": state.phase,
        "top_deltas": trainer.top_theta_deltas(5),
    }


@router.post("/preference/export-yaml")
def preference_export_yaml(req: ExportYamlRequest) -> dict:
    from colayout.preference.theta import _kind_default_weight
    from colayout.relations.loader import relation_kinds as load_relation_kinds

    trainer = PreferenceTrainer(req.room_type)
    state = trainer.load_state()
    if not RELATIONS_PATH.is_file():
        raise HTTPException(status_code=500, detail="Relations config missing")

    theta_payload = {
        "version": 1,
        "room_type": req.room_type,
        "theta": {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in state.theta_current.items()
        },
    }
    THETA_LEARNED_PATH.write_text(
        yaml.dump(theta_payload, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    kinds = load_relation_kinds()
    kind_to_ip: dict[str, str] = {
        name: spec.ip_type for name, spec in kinds.items()
    }

    with RELATIONS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    updated = 0
    for role, body in (data.get("roles") or {}).items():
        for rule in body.get("relations") or []:
            if rule.get("hard", False):
                continue
            room_types = rule.get("room_types") or []
            if req.room_type not in room_types and "*" not in room_types:
                continue
            kind = rule.get("kind")
            ip_type = kind_to_ip.get(kind or "")
            if ip_type:
                kkey = f"{req.room_type}.kind.{ip_type}.weight"
                learned = state.theta_current.get(kkey)
                if learned is not None:
                    default_w = _kind_default_weight(ip_type)
                    if default_w > 0:
                        scale = learned / default_w
                        base = rule.get("weight")
                        if base is None:
                            base = default_w
                        rule["weight"] = round(float(base) * scale, 2)
                        updated += 1
            dkey_map = {
                "in_front_of": {
                    "chair": "metric.chair_desk_dist_m",
                    "coffee_table": "metric.sofa_coffee_dist_m",
                    "bar_stool": "metric.bar_stool_dist_m",
                }
            }
            if kind == "in_front_of" and role in dkey_map.get("in_front_of", {}):
                mkey = dkey_map["in_front_of"][role]
                if mkey in state.theta_current:
                    rule["distance_m"] = round(state.theta_current[mkey], 3)
                    updated += 1

    LEARNED_RELATIONS_PATH.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return {
        "theta_path": str(THETA_LEARNED_PATH.relative_to(ROOT)),
        "relations_path": str(LEARNED_RELATIONS_PATH.relative_to(ROOT)),
        "updated_rules": updated,
        "room_type": req.room_type,
    }
