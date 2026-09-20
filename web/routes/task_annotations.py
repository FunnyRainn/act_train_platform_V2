"""三任务原始标注及数据集导出接口；与旧矩形接口并存。"""
from fastapi import APIRouter, Request
from core import task_annotations as annotations
from core.task_dataset import export_set
from core.task_importer import import_set, inspect_source
from web.context import api_error

router = APIRouter()


@router.post("/api/task-datasets/inspect")
async def inspect_dataset(request: Request):
    """只读预检任务和类别映射，让页面先展示导入规模及限制。"""
    try:
        payload=await request.json()
        spec,frames=inspect_source(payload["project_id"],payload["task_type"],payload["source_dir"])
        return {**spec,"frame_count":len(frames),"source_preserved":True}
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/task-datasets/import")
async def import_dataset(request: Request):
    """显式导入只写当前数据根，原目录保持不变。"""
    try:
        payload=await request.json()
        return import_set(payload["project_id"],payload["name"],payload["task_type"],payload["source_dir"])
    except Exception as exc:
        raise api_error(exc)


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
        return export_set(set_id, payload.get("name", ""), payload.get("focus_region_id"), payload.get("split_by_video"))
    except Exception as exc:
        raise api_error(exc)
