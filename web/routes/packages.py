from __future__ import annotations

import subprocess

from fastapi import APIRouter, Request

from core import store, training_ops
from core.runtime_paths import resolve_runtime_path
from web.context import api_error

router = APIRouter()


@router.get("/api/model-packages")
def list_model_packages(project_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_model_packages` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_model_packages(project_id)


@router.post("/api/model-packages")
async def create_model_package(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `create_model_package` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return training_ops.export_model_package(payload["train_job_id"], payload.get("name") or "模型包")
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/model-packages/{package_id}/open-folder")
def open_model_package_folder(package_id: str) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `open_model_package_folder` 的职责和调用边界。
    入参：package_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        package = store.get_model_package(package_id)
        package_dir = resolve_runtime_path(package["package_dir"], "模型目录", require_exists=True)
        subprocess.Popen(["explorer.exe", str(package_dir)])
        return {"package_id": package_id, "opened": True, "package_dir": str(package_dir)}
    except Exception as exc:
        raise api_error(exc)
