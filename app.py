from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import annotation_ops, dataset_ops, prelabel_ops, store, training_ops, video_ops
from core.db import init_db
from core.paths import PROJECT_ROOT


app = FastAPI(title="act_train_platform", version="1.0.0.10")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def page(request: Request, template: str, **context: Any) -> HTMLResponse:
    context.setdefault("version", "v1.0.0.10")
    return templates.TemplateResponse(request, template, context)


def api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return page(request, "index.html", page_id="overview")


@app.get("/labels", response_class=HTMLResponse)
def labels_page(request: Request) -> HTMLResponse:
    return page(request, "labels.html", page_id="labels")


@app.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request) -> HTMLResponse:
    return page(request, "projects.html", page_id="projects")


@app.get("/videos", response_class=HTMLResponse)
def videos_page(request: Request) -> HTMLResponse:
    return page(request, "videos.html", page_id="videos")


@app.get("/annotate", response_class=HTMLResponse)
def annotate_page(request: Request) -> HTMLResponse:
    return page(request, "annotate.html", page_id="annotate")


@app.get("/datasets", response_class=HTMLResponse)
def datasets_page(request: Request) -> HTMLResponse:
    return page(request, "datasets.html", page_id="datasets")


@app.get("/training", response_class=HTMLResponse)
def training_page(request: Request) -> HTMLResponse:
    return page(request, "training.html", page_id="training")


@app.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request) -> HTMLResponse:
    return page(request, "packages.html", page_id="packages")


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    return {
        "labels": store.list_labels(),
        "projects": store.list_projects(),
        "video_assets": store.list_video_assets(),
        "videos": store.list_videos(),
        "frame_sets": store.list_frame_sets(),
        "datasets": store.list_dataset_versions(),
        "train_jobs": training_ops.list_train_jobs_with_progress(),
        "packages": store.list_model_packages(),
    }


@app.get("/api/labels")
def list_labels() -> list[dict]:
    return store.list_labels()


@app.post("/api/labels")
async def save_label(request: Request) -> dict:
    try:
        return store.upsert_label(await request.json())
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return store.list_projects()


@app.post("/api/projects")
async def save_project(request: Request) -> dict:
    try:
        return store.save_project(await request.json())
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/videos")
def list_videos(project_id: str | None = None) -> list[dict]:
    return store.list_videos(project_id)


@app.get("/api/video-assets")
def list_video_assets() -> list[dict]:
    return store.list_video_assets()


@app.post("/api/videos/upload")
async def upload_video(project_id: str = Form(...), file: UploadFile = File(...)) -> dict:
    try:
        data = await file.read()
        return video_ops.register_uploaded_video(project_id, file.filename or "video.mp4", data)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/videos/import")
async def import_video(request: Request) -> dict:
    try:
        payload = await request.json()
        return video_ops.register_imported_video(
            payload["project_id"],
            payload["path"],
            bool(payload.get("copy_to_platform", False)),
        )
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/frame-sets/extract")
async def extract_frames(request: Request) -> dict:
    try:
        payload = await request.json()
        return video_ops.extract_frames(
            payload["video_id"],
            int(payload.get("sample_every_n_frames") or 5),
            int(payload.get("max_frames") or 0),
            int(payload.get("jpeg_quality") or 95),
            payload.get("name"),
            bool(payload.get("overwrite", False)),
        )
    except Exception as exc:
        raise api_error(exc)


@app.delete("/api/frame-sets/{frame_set_id}")
def delete_frame_set(frame_set_id: str) -> dict:
    try:
        return store.delete_frame_set(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/frame-sets")
def list_frame_sets(project_id: str | None = None) -> list[dict]:
    return store.list_frame_sets(project_id)


@app.get("/api/frame-sets/{frame_set_id}/frames")
def list_frames(frame_set_id: str) -> list[dict]:
    try:
        return store.list_frames(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/frames/{frame_id}/image")
def frame_image(frame_id: str) -> FileResponse:
    try:
        frame = store.get_frame(frame_id)
        path = Path(frame["path"])
        if not path.exists():
            raise FileNotFoundError(path)
        return FileResponse(path)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/frame-sets/{frame_set_id}/annotations")
def list_annotations(frame_set_id: str, frame_id: str | None = None) -> list[dict]:
    try:
        return store.list_annotations(frame_set_id, frame_id)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/annotations/frame")
async def save_frame_annotations(request: Request) -> list[dict]:
    try:
        payload = await request.json()
        return store.replace_frame_annotations(
            payload["project_id"],
            payload["frame_set_id"],
            payload["frame_id"],
            payload.get("annotations") or [],
        )
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/tracks")
async def create_track(request: Request) -> dict:
    try:
        payload = await request.json()
        return store.create_or_get_track(payload["project_id"], payload["frame_set_id"], payload["label_code"], payload.get("track_id"))
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/frame-sets/{frame_set_id}/tracks")
def list_tracks(frame_set_id: str) -> list[dict]:
    try:
        return store.list_tracks(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/tracks/{track_id}/interpolate")
async def interpolate_track(track_id: str, request: Request) -> dict:
    try:
        payload = await request.json()
        return annotation_ops.interpolate_track(payload["frame_set_id"], track_id)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/prelabel")
async def prelabel(request: Request) -> dict:
    try:
        payload = await request.json()
        return prelabel_ops.run_prelabel(payload["frame_set_id"], payload["model_path"], float(payload.get("conf") or 0.25))
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/prelabel/clear")
async def clear_prelabel(request: Request) -> dict:
    try:
        payload = await request.json()
        return prelabel_ops.clear_unconfirmed_prelabels(payload["frame_set_id"])
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/datasets")
def list_datasets(project_id: str | None = None) -> list[dict]:
    return store.list_dataset_versions(project_id)


@app.post("/api/datasets/export")
async def export_dataset(request: Request) -> dict:
    try:
        payload = await request.json()
        return dataset_ops.export_dataset(
            payload["project_id"],
            payload.get("name") or "数据集版本",
            payload.get("frame_set_ids") or [],
            payload.get("history_dataset_ids") or [],
            bool(payload.get("annotated_only")),
        )
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/train-jobs")
def list_train_jobs(project_id: str | None = None) -> list[dict]:
    return training_ops.list_train_jobs_with_progress(project_id)


@app.post("/api/train-jobs")
async def create_train_job(request: Request) -> dict:
    try:
        payload = await request.json()
        return training_ops.create_train_job(
            payload["project_id"],
            payload["dataset_version_id"],
            payload.get("name") or "训练任务",
            payload.get("base_model_path") or "yolo11m.pt",
            payload.get("params") or {},
        )
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/train-jobs/{job_id}")
def get_train_job(job_id: str) -> dict:
    try:
        return training_ops.get_train_job_with_progress(job_id)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/train-jobs/{job_id}/stop")
def stop_train_job(job_id: str) -> dict:
    try:
        return training_ops.stop_train_job(job_id)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/gpu-status")
def gpu_status() -> dict:
    return training_ops.read_gpu_status()


@app.get("/api/model-packages")
def list_model_packages(project_id: str | None = None) -> list[dict]:
    return store.list_model_packages(project_id)


@app.post("/api/model-packages")
async def create_model_package(request: Request) -> dict:
    try:
        payload = await request.json()
        return training_ops.export_model_package(payload["train_job_id"], payload.get("name") or "模型包")
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/model-packages/{package_id}/open-folder")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 act_train_platform")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18100)
    args = parser.parse_args()
    uvicorn.run("app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
