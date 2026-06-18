from __future__ import annotations

from fastapi import APIRouter, Request

from core import dataset_ops, store
from core.datasets import yolo_importer
from web.context import api_error

router = APIRouter()


@router.get("/api/datasets")
def list_datasets(project_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_datasets` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_dataset_versions(project_id)


@router.post("/api/datasets/export")
async def export_dataset(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `export_dataset` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

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


@router.post("/api/datasets/import-yolo/inspect")
async def inspect_yolo_dataset(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `inspect_yolo_dataset` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return yolo_importer.inspect_yolo_dataset(payload["project_id"], payload["dataset_dir"])
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/datasets/import-yolo")
async def import_yolo_dataset(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `import_yolo_dataset` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return yolo_importer.import_yolo_dataset(
            payload["project_id"],
            payload.get("name") or "外部YOLO数据集",
            payload["dataset_dir"],
            payload.get("label_mapping") or {},
            payload.get("image_scope") or "full_image",
            payload.get("focus_region_id") or None,
        )
    except Exception as exc:
        raise api_error(exc)
