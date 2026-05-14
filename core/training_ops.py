from __future__ import annotations

import json
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from . import store
from .db import json_dumps
from .paths import PACKAGES_DIR, RUNS_DIR
from .utils import clean_dir, new_id, now_text, safe_name


EXECUTOR = ThreadPoolExecutor(max_workers=1)


def create_train_job(project_id: str, dataset_version_id: str, name: str, base_model_path: str, params: dict[str, Any]) -> dict:
    dataset = store.get_dataset_version(dataset_version_id)
    job_id = new_id("train")
    output_dir = RUNS_DIR / project_id / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    job = store.save_train_job(
        {
            "id": job_id,
            "project_id": project_id,
            "dataset_version_id": dataset_version_id,
            "name": name,
            "base_model_path": base_model_path,
            "output_dir": output_dir,
            "status": "queued",
            "params": params,
        }
    )
    EXECUTOR.submit(_run_train_job, job["id"], dataset, params)
    return job


def _run_train_job(job_id: str, dataset: dict, params: dict[str, Any]) -> None:
    try:
        from ultralytics import YOLO

        job = store.get_train_job(job_id)
        store.update_train_job(job_id, status="running", started_at=now_text(), log_text="训练已启动")
        data_yaml = Path(dataset["output_dir"]) / "dataset.generated.yaml"
        model = YOLO(job["base_model_path"])
        train_kwargs = {
            "data": str(data_yaml),
            "project": str(Path(job["output_dir"])),
            "name": "train",
            "exist_ok": True,
            "epochs": int(params.get("epochs") or 50),
            "imgsz": int(params.get("imgsz") or 1280),
            "batch": int(params.get("batch") or 8),
            "device": str(params.get("device") or "0"),
            "workers": int(params.get("workers") or 4),
            "patience": int(params.get("patience") or 30),
            "plots": True,
            "val": True,
        }
        result = model.train(**train_kwargs)
        metrics = {"result_type": type(result).__name__, "train_kwargs": train_kwargs}
        store.update_train_job(
            job_id,
            status="finished",
            finished_at=now_text(),
            metrics_json=json_dumps(metrics),
            log_text="训练完成，请检查输出目录中的 weights/best.pt 和 results.csv",
        )
    except Exception as exc:
        store.update_train_job(
            job_id,
            status="failed",
            finished_at=now_text(),
            log_text=f"{exc}\n{traceback.format_exc()}",
        )


def export_model_package(train_job_id: str, name: str) -> dict:
    job = store.get_train_job(train_job_id)
    if job["status"] != "finished":
        raise ValueError("训练任务未完成，不能导出模型包")
    dataset = store.get_dataset_version(job["dataset_version_id"])
    project = store.get_project(job["project_id"])
    job_dir = Path(job["output_dir"])
    best_pt = job_dir / "train" / "weights" / "best.pt"
    if not best_pt.exists():
        raise FileNotFoundError(f"未找到 best.pt: {best_pt}")

    package_id = new_id("package")
    package_dir = PACKAGES_DIR / project["id"] / f"{package_id}_{safe_name(name)}"
    clean_dir(package_dir)
    shutil.copy2(best_pt, package_dir / "best.pt")

    labels_yaml = {"names": {idx: code for idx, code in enumerate(dataset["label_codes"])}}
    (package_dir / "labels.yaml").write_text(yaml.safe_dump(labels_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")

    metadata = {
        "package_id": package_id,
        "name": name,
        "project_id": project["id"],
        "project_name": project["name"],
        "train_job_id": train_job_id,
        "dataset_version_id": dataset["id"],
        "label_codes": dataset["label_codes"],
        "created_at": now_text(),
    }
    (package_dir / "package.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "dataset_version.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "train_report.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "preview_examples").mkdir(exist_ok=True)

    return store.save_model_package(
        {
            "id": package_id,
            "project_id": project["id"],
            "train_job_id": train_job_id,
            "name": name,
            "package_dir": package_dir,
            "status": "ready",
            "metadata": metadata,
        }
    )
