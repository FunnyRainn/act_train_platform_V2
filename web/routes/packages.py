from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Request

from core import store, training_ops
from web.context import api_error

router = APIRouter()


@router.get("/api/model-packages")
def list_model_packages(project_id: str | None = None) -> list[dict]:
    return store.list_model_packages(project_id)


@router.post("/api/model-packages")
async def create_model_package(request: Request) -> dict:
    try:
        payload = await request.json()
        return training_ops.export_model_package(payload["train_job_id"], payload.get("name") or "模型包")
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/model-packages/{package_id}/open-folder")
def open_model_package_folder(package_id: str) -> dict:
    try:
        package = store.get_model_package(package_id)
        package_dir = Path(package["package_dir"])
        if not package_dir.exists():
            raise FileNotFoundError("模型目录不存在，可能已被移动或删除")
        subprocess.Popen(["explorer.exe", str(package_dir)])
        return {"package_id": package_id, "opened": True, "package_dir": str(package_dir)}
    except Exception as exc:
        raise api_error(exc)
