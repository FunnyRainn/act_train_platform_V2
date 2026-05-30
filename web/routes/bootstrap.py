from __future__ import annotations

from fastapi import APIRouter

from core import store, training_ops

router = APIRouter()


@router.get("/api/bootstrap")
def bootstrap() -> dict:
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
