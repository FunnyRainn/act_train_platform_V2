from __future__ import annotations

from fastapi import APIRouter, Request

from core import dataset_ops, store
from web.context import api_error

router = APIRouter()


@router.get("/api/datasets")
def list_datasets(project_id: str | None = None) -> list[dict]:
    return store.list_dataset_versions(project_id)


@router.post("/api/datasets/export")
async def export_dataset(request: Request) -> dict:
    try:
        payload = await request.json()
        return dataset_ops.export_dataset(
            payload["project_id"],
            payload.get("name") or "训练数据集版本",
            payload.get("frame_set_ids") or [],
            payload.get("history_dataset_ids") or [],
            bool(payload.get("annotated_only")),
            payload.get("image_scope") or "full_image",
            payload.get("focus_region_ids") or [],
            payload.get("history_by_focus_region") or {},
            bool(payload.get("force_mixed_scope", False)),
        )
    except Exception as exc:
        raise api_error(exc)
