from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from core import training_ops
from web.context import api_error

router = APIRouter()

DEFAULT_BASE_MODEL = "yolo11m.pt"


def _resolve_base_model_path(raw_value: object) -> str:
    """用途：说明 Web 路由、请求校验和页面 API 中 `_resolve_base_model_path` 的职责和调用边界。
    入参：raw_value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    raw = str(raw_value or "").strip()
    if not raw:
        return DEFAULT_BASE_MODEL
    path = Path(raw)
    # 自定义预训练模型必须是服务端本机绝对路径，前端只负责传入字符串。
    if not path.is_absolute():
        raise ValueError("预训练模型路径必须是训练服务所在机器上的绝对路径。")
    if path.suffix.lower() != ".pt":
        raise ValueError("预训练模型文件必须是 .pt 文件。")
    if not path.is_file():
        raise FileNotFoundError(f"预训练模型文件不存在：{raw}")
    return str(path)


@router.get("/api/train-jobs")
def list_train_jobs(project_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_train_jobs` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return training_ops.list_train_jobs_with_progress(project_id)


@router.post("/api/train-jobs")
async def create_train_job(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `create_train_job` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        # 路由层只做请求字段拆解和模型路径校验，训练任务状态由 core.training_ops 负责落库。
        return training_ops.create_train_job(
            payload["project_id"],
            payload["dataset_version_id"],
            payload.get("name") or "模型训练任务",
            _resolve_base_model_path(payload.get("base_model_path")),
            payload.get("params") or {},
        )
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/train-jobs/{job_id}")
def get_train_job(job_id: str) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `get_train_job` 的职责和调用边界。
    入参：job_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return training_ops.get_train_job_with_progress(job_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/train-jobs/{job_id}/stop")
def stop_train_job(job_id: str) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `stop_train_job` 的职责和调用边界。
    入参：job_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return training_ops.stop_train_job(job_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/gpu-status")
def gpu_status() -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `gpu_status` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return training_ops.read_gpu_status()
