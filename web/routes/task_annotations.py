"""三任务原始标注及数据集导出接口；与旧矩形接口并存。"""
from fastapi import APIRouter, Request
from core import task_annotations as annotations
from core.task_dataset import export_set
from web.context import api_error

router = APIRouter()


@router.get("/api/annotation-sets")
def list_sets(project_id: str):
    return annotations.list_sets(project_id)


@router.post("/api/annotation-sets")
async def create_set(request: Request):
    try:
        payload = await request.json()
        return annotations.create_set(payload["project_id"], payload["name"], payload["task_type"], payload.get("label_codes"))
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/annotation-sets/{set_id}/frames/{frame_id}")
def read_frame(set_id: str, frame_id: str):
    try:
        return annotations.read_annotation(set_id, frame_id)
    except Exception as exc:
        raise api_error(exc)


@router.put("/api/annotation-sets/{set_id}/frames/{frame_id}")
async def save_frame(set_id: str, frame_id: str, request: Request):
    try:
        return annotations.save_annotation(set_id, frame_id, await request.json())
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/annotation-sets/{set_id}/export")
async def export_dataset(set_id: str, request: Request):
    try:
        payload = await request.json()
        return export_set(set_id, payload.get("name", ""), payload.get("focus_region_id"))
    except Exception as exc:
        raise api_error(exc)
