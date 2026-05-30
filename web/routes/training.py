from __future__ import annotations

from fastapi import APIRouter, Request

from core import training_ops
from web.context import api_error

router = APIRouter()


@router.get("/api/train-jobs")
def list_train_jobs(project_id: str | None = None) -> list[dict]:
    return training_ops.list_train_jobs_with_progress(project_id)


@router.post("/api/train-jobs")
async def create_train_job(request: Request) -> dict:
    try:
        payload = await request.json()
        return training_ops.create_train_job(
            payload["project_id"],
            payload["dataset_version_id"],
            payload.get("name") or "模型训练任务",
            payload.get("base_model_path") or "yolo11m.pt",
            payload.get("params") or {},
        )
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/train-jobs/{job_id}")
def get_train_job(job_id: str) -> dict:
    try:
        return training_ops.get_train_job_with_progress(job_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/train-jobs/{job_id}/stop")
def stop_train_job(job_id: str) -> dict:
    try:
        return training_ops.stop_train_job(job_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/gpu-status")
def gpu_status() -> dict:
    return training_ops.read_gpu_status()
