from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from colayout.assets import label_store
from colayout.assets.kenney import load_kenney_catalog

router = APIRouter(prefix="/api/orientation")


class LabelBody(BaseModel):
    front_dir: list[float] = Field(min_length=2, max_length=2)
    wall_anchor: str | None = None


@router.get("/labels")
def get_labels() -> dict:
    data = label_store.load_label_store()
    assets = load_kenney_catalog().get("assets", [])
    progress = label_store.progress_counts(len(assets))
    return {
        "labels": data.get("labels", {}),
        "skipped": data.get("skipped", []),
        "progress": progress,
    }


@router.get("/models")
def list_models() -> list[dict]:
    catalog = load_kenney_catalog()
    labels = label_store.load_label_store().get("labels", {})
    skipped = label_store.list_skipped()
    rows: list[dict] = []
    for a in catalog.get("assets", []):
        mid = a["id"]
        rows.append(
            {
                "id": mid,
                "role": a.get("role", "decor"),
                "category": a.get("category", "misc"),
                "width_m": a.get("width_m", 1),
                "depth_m": a.get("depth_m", 1),
                "has_label": mid in labels,
                "skipped": mid in skipped,
            }
        )
    return rows


@router.put("/labels/{model_id}")
def put_label(model_id: str, body: LabelBody) -> dict:
    catalog = load_kenney_catalog()
    if model_id not in {a["id"] for a in catalog.get("assets", [])}:
        raise HTTPException(status_code=404, detail=f"Unknown model_id '{model_id}'")
    try:
        entry = label_store.save_label(
            model_id, body.front_dir, body.wall_anchor
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"model_id": model_id, "label": entry}


@router.post("/skip/{model_id}")
def skip_model(model_id: str) -> dict:
    catalog = load_kenney_catalog()
    if model_id not in {a["id"] for a in catalog.get("assets", [])}:
        raise HTTPException(status_code=404, detail=f"Unknown model_id '{model_id}'")
    label_store.skip_model(model_id)
    return {"model_id": model_id, "skipped": True}


@router.delete("/labels/{model_id}")
def delete_label(model_id: str) -> dict:
    label_store.clear_label(model_id)
    return {"model_id": model_id, "cleared": True}
