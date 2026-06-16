"""Cached LLM-only layout drafts for preference training and few-shot examples."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colayout.grid.discretize import discretize_room
from colayout.llm.draft_to_hints import draft_to_scene_graph, placement_result_from_draft
from colayout.llm.few_shot import few_shot_golden_ids
from colayout.llm.provider import LLMProvider, get_llm_provider
from colayout.llm.validate_placement import validate_layout_draft
from colayout.placement.orient import apply_facing_orientations
from colayout.preference.store import ROOT
from colayout.schemas.architecture import RoomArchitecture, default_architecture
from colayout.schemas.floor import RoomSpec
from colayout.schemas.layout_draft import RoomLayoutDraft

logger = logging.getLogger(__name__)

LLM_DESIGNS_DIR = ROOT / "data" / "preference" / "llm_designs"
PREFERENCE_ROOM_TYPES = ("bedroom", "living_room", "kitchen")
# (min_w, min_l), (max_w, max_l) in metres
ROOM_SIZE_RANGES: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "bedroom": ((3.2, 2.8), (5.5, 4.5)),
    "living_room": ((3.5, 3.0), (6.5, 5.5)),
    "kitchen": ((4.0, 3.5), (6.0, 5.0)),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir() -> None:
    LLM_DESIGNS_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(design_id: str) -> Path:
    return LLM_DESIGNS_DIR / f"{design_id}.json"


def design_id_for(room_type: str, index: int) -> str:
    return f"{room_type}_{index:02d}"


def random_room_spec(
    room_type: str,
    design_id: str,
    rng: random.Random,
) -> RoomSpec:
    (wmin, lmin), (wmax, lmax) = ROOM_SIZE_RANGES[room_type]
    width_m = round(rng.uniform(wmin, wmax), 1)
    length_m = round(rng.uniform(lmin, lmax), 1)
    arch = default_architecture(room_type, width_m, length_m)
    return RoomSpec(
        id=design_id,
        type=room_type,
        width_m=width_m,
        length_m=length_m,
        architecture=arch,
    )


def room_from_design(record: dict[str, Any]) -> RoomSpec:
    arch = record.get("architecture")
    return RoomSpec(
        id=record.get("design_id", "design"),
        type=record["room_type"],
        width_m=float(record["width_m"]),
        length_m=float(record["length_m"]),
        architecture=RoomArchitecture.model_validate(arch) if arch else None,
    )


def load_cached_llm_design(design_id: str) -> dict[str, Any] | None:
    path = _cache_path(design_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cached_llm_design(record: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir()
    did = record["design_id"]
    path = _cache_path(did)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)
    return record


def list_cached_llm_designs(room_type: str | None = None) -> list[dict[str, Any]]:
    _ensure_dir()
    out: list[dict[str, Any]] = []
    for path in sorted(LLM_DESIGNS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rtype = data.get("room_type")
        if room_type and rtype != room_type:
            continue
        did = data.get("design_id", path.stem)
        out.append(
            {
                "design_id": did,
                "room_type": rtype,
                "width_m": data.get("width_m"),
                "length_m": data.get("length_m"),
                "generated_at": data.get("generated_at"),
                "few_shot_ids": data.get("few_shot_ids") or [],
                "mock_llm": bool(data.get("mock_llm", False)),
                "placement_count": len(
                    (data.get("draft") or {}).get("placements") or []
                ),
            }
        )
    return out


def pick_random_design_id(
    room_type: str,
    rng: random.Random | None = None,
) -> str | None:
    """Return a random cached design id for the room type."""
    designs = list_cached_llm_designs(room_type)
    if not designs:
        return None
    rng = rng or random.Random()
    return rng.choice(designs)["design_id"]


def generate_and_cache_design(
    design_id: str,
    room: RoomSpec,
    llm: LLMProvider | None = None,
    *,
    use_mock: bool = False,
    modulor_cell_m: float = 0.25,
) -> dict[str, Any]:
    """Run llm_only planner with cached LLM-design few-shot for a random room."""
    provider = llm or get_llm_provider(use_mock=use_mock)
    few_shot_ids = few_shot_golden_ids(room.type)
    draft = provider.generate_layout_draft(room)
    draft, val_errors = validate_layout_draft(draft, room)
    warnings = list(getattr(provider, "last_generation_warnings", None) or [])
    warnings.extend(val_errors)

    grid = discretize_room(room, modulor_cell_m)
    graph = draft_to_scene_graph(draft, room)
    placement = apply_facing_orientations(
        placement_result_from_draft(draft, grid), graph
    )

    record = {
        "design_id": design_id,
        "room_type": room.type,
        "width_m": room.width_m,
        "length_m": room.length_m,
        "architecture": (
            room.architecture.model_dump() if room.architecture else None
        ),
        "draft": draft.model_dump(),
        "layout": placement.model_dump(),
        "few_shot_ids": few_shot_ids,
        "mock_llm": use_mock or provider.__class__.__name__ == "MockLLMProvider",
        "warnings": warnings,
        "generated_at": _now_iso(),
    }
    return save_cached_llm_design(record)


def cache_random_designs(
    *,
    per_type: int = 3,
    use_mock: bool = False,
    seed: int = 42,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """Generate and cache ``per_type`` random-room LLM designs per room type."""
    rng = random.Random(seed)
    llm = get_llm_provider(use_mock=use_mock)
    saved: list[dict[str, Any]] = []

    for room_type in PREFERENCE_ROOM_TYPES:
        for i in range(1, per_type + 1):
            design_id = design_id_for(room_type, i)
            if not overwrite and load_cached_llm_design(design_id) is not None:
                logger.info("Skip existing %s", design_id)
                cached = load_cached_llm_design(design_id)
                if cached:
                    saved.append(cached)
                continue
            room = random_room_spec(room_type, design_id, rng)
            logger.info(
                "Generating %s (%s %.1f×%.1f m)",
                design_id,
                room_type,
                room.width_m,
                room.length_m,
            )
            saved.append(
                generate_and_cache_design(
                    design_id, room, llm, use_mock=use_mock
                )
            )
    return saved


def draft_from_cached(cached: dict[str, Any]) -> RoomLayoutDraft:
    draft = cached["draft"]
    return RoomLayoutDraft.model_validate(
        {
            **draft,
            "room_id": draft.get("room_id") or cached["design_id"],
            "room_type": draft.get("room_type") or cached["room_type"],
        }
    )
