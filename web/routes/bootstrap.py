from __future__ import annotations

from fastapi import APIRouter

from core import store, training_ops

router = APIRouter()


@router.get("/api/bootstrap")
def bootstrap() -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `bootstrap` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return {
        "labels": store.list_labels(),
        "projects": store.list_projects(),
        "video_assets": store.list_video_assets(),
        "videos": store.list_videos(),
        "frame_sets": store.list_frame_sets(),
        "focus_regions": store.list_focus_regions(),
        "datasets": store.list_dataset_versions(),
        "train_jobs": training_ops.list_train_jobs_with_progress(),
        "packages": store.list_model_packages(),
    }
