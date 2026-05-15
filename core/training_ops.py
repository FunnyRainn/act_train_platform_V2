from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import store
from .db import json_dumps
from .paths import PACKAGES_DIR, PROJECT_ROOT, RUNS_DIR
from .utils import clean_dir, new_id, now_text, safe_name


def create_train_job(project_id: str, dataset_version_id: str, name: str, base_model_path: str, params: dict[str, Any]) -> dict:
    store.get_dataset_version(dataset_version_id)
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
            "progress": {"current_epoch": 0, "total_epochs": int(params.get("epochs") or 50), "percent": 0},
        }
    )
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "core.train_worker", job_id],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    store.update_train_job(job_id, process_id=process.pid)
    return get_train_job_with_progress(job_id)


def stop_train_job(job_id: str) -> dict:
    job = store.get_train_job(job_id)
    pid = int(job.get("process_id") or 0)
    if pid > 0:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        else:
            os.kill(pid, 15)
    store.update_train_job(
        job_id,
        status="stopped",
        finished_at=now_text(),
        log_text=(job.get("log_text") or "") + "\n用户已停止训练。",
        process_id=0,
    )
    return get_train_job_with_progress(job_id)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            pass
    return None


def _read_results_csv(job: dict) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(job["output_dir"]) / "train" / "results.csv"
    if not path.exists():
        return [], {}
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {str(k).strip(): v for k, v in row.items() if k is not None}
            rows.append(cleaned)
    if not rows:
        return [], {}
    return rows, rows[-1]


def _available_model_files(job: dict) -> dict[str, str]:
    weights_dir = Path(job["output_dir"]) / "train" / "weights"
    files: dict[str, str] = {}
    for name in ["best.pt", "last.pt"]:
        path = weights_dir / name
        if path.exists():
            files[name] = str(path)
    return files


def _existing_package_for_job(train_job_id: str) -> dict[str, Any] | None:
    for package in store.list_model_packages():
        if package.get("train_job_id") == train_job_id:
            return package
    return None


def _default_package_name(job: dict[str, Any]) -> str:
    project = store.get_project(job["project_id"])
    product_name = project.get("product_name") or project.get("name") or "通用检测模型"
    return f"{product_name}-{job.get('name') or job['id']}"


def get_train_job_with_progress(job_id: str, auto_package: bool = True) -> dict:
    job = store.get_train_job(job_id)
    rows, last = _read_results_csv(job)
    total = int(job["params"].get("epochs") or job.get("progress", {}).get("total_epochs") or 0)
    current = len(rows)
    percent = round((current / total) * 100, 1) if total else 0
    started = _parse_datetime(job.get("started_at"))
    eta_seconds = None
    if started and current > 0 and total and current < total:
        elapsed = max(1, (datetime.now() - started).total_seconds())
        eta_seconds = int((elapsed / current) * (total - current))
    model_files = _available_model_files(job)
    job["progress"] = {
        "current_epoch": current,
        "total_epochs": total,
        "percent": percent,
        "eta_seconds": eta_seconds,
        "last_metrics": last,
        "series": rows[-200:],
        "model_files": model_files,
    }
    if auto_package and job.get("status") in {"finished", "stopped"} and model_files:
        try:
            job["model_package"] = ensure_model_package_for_job(job_id)
        except Exception as exc:
            job["model_package_error"] = str(exc)
    return job


def list_train_jobs_with_progress(project_id: str | None = None) -> list[dict]:
    return [get_train_job_with_progress(job["id"]) for job in store.list_train_jobs(project_id)]


def ensure_model_package_for_job(job_id: str) -> dict[str, Any] | None:
    job = get_train_job_with_progress(job_id, auto_package=False)
    if job.get("status") not in {"finished", "stopped"}:
        return None
    if not (job.get("progress", {}).get("model_files") or {}):
        return None
    existing = _existing_package_for_job(job_id)
    if existing:
        return existing
    return export_model_package(job_id, _default_package_name(job), auto_package=False)


def read_gpu_status() -> dict:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        gpus = []
        for line in result.stdout.strip().splitlines():
            name, total, used, free, util = [part.strip() for part in line.split(",")]
            gpus.append(
                {
                    "name": name,
                    "memory_total_mb": int(float(total)),
                    "memory_used_mb": int(float(used)),
                    "memory_free_mb": int(float(free)),
                    "utilization_gpu": int(float(util)),
                }
            )
        return {"ok": True, "gpus": gpus}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "gpus": []}


def export_model_package(train_job_id: str, name: str, auto_package: bool = True) -> dict:
    existing = _existing_package_for_job(train_job_id)
    if existing:
        return existing
    job = get_train_job_with_progress(train_job_id, auto_package=auto_package)
    model_files = job["progress"].get("model_files") or {}
    selected = model_files.get("best.pt") or model_files.get("last.pt")
    if not selected:
        raise FileNotFoundError("当前训练任务没有可用模型文件，不能生成模型目录。")
    dataset = store.get_dataset_version(job["dataset_version_id"])
    project = store.get_project(job["project_id"])
    package_id = new_id("package")
    package_dir = PACKAGES_DIR / project["id"] / f"{package_id}_{safe_name(name)}"
    clean_dir(package_dir)

    default_weight = "best.pt" if model_files.get("best.pt") else "last.pt"
    shutil.copy2(selected, package_dir / default_weight)
    if model_files.get("last.pt") and default_weight != "last.pt":
        shutil.copy2(model_files["last.pt"], package_dir / "last.pt")

    label_rows = [label for label in store.list_labels() if label["code"] in dataset["label_codes"]]
    label_names = {idx: code for idx, code in enumerate(dataset["label_codes"])}
    (package_dir / "labels.yaml").write_text(yaml.safe_dump({"names": label_names}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (package_dir / "label_policy.json").write_text(json.dumps(label_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "1.0",
        "package_id": package_id,
        "package_name": name,
        "default_weight": default_weight,
        "label_codes": dataset["label_codes"],
        "labels": label_rows,
        "source_product": {"id": project["id"], "name": project["name"], "product_name": project.get("product_name", "")},
        "train_job_id": train_job_id,
        "dataset_version_id": dataset["id"],
        "recommended": {
            "imgsz": int(job["params"].get("imgsz") or 1280),
            "conf": float(job["params"].get("conf") or 0.35),
        },
        "created_at": now_text(),
    }
    (package_dir / "model_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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
            "metadata": manifest,
        }
    )
