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

from core import store
from core.paths import PACKAGES_DIR, PROJECT_ROOT, RUNS_DIR
from core.runtime_paths import repair_dataset_artifacts, resolve_runtime_path
from core.utils import clean_dir, new_id, now_text, safe_name


WORKER_LOG_NAME = "worker.log"


def create_train_job(project_id: str, dataset_version_id: str, name: str, base_model_path: str, params: dict[str, Any]) -> dict:
    """用途：说明 训练任务、训练进度和模型包导出 中 `create_train_job` 的职责和调用边界。
    入参：project_id、dataset_version_id、name、base_model_path、params，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    dataset = store.get_dataset_version(dataset_version_id)
    repair_dataset_artifacts(dataset["output_dir"])
    params = dict(params or {})
    dataset_metadata = dataset.get("metadata") or {}
    recommended_imgsz = int(dataset_metadata.get("recommended_imgsz") or (dataset.get("summary") or {}).get("recommended_imgsz") or 1280)
    raw_imgsz = params.get("imgsz")
    if raw_imgsz in {None, "", 0, "0", "auto"}:
        # 页面留空或选择 auto 时使用数据集推荐尺寸，避免把内部默认值暴露给客户操作。
        params["imgsz"] = recommended_imgsz
        params["auto_imgsz"] = True
    else:
        params["imgsz"] = int(raw_imgsz)
        params["auto_imgsz"] = False
    params["recommended_imgsz"] = recommended_imgsz

    job_id = new_id("train")
    output_dir = RUNS_DIR / project_id / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    store.save_train_job(
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
    if getattr(sys, "frozen", False):
        # 打包态通过同一个 exe 拉起训练 worker，保证现场部署不依赖源码模块路径。
        worker_command = [sys.executable, "--train-worker", job_id]
    else:
        worker_command = [sys.executable, "-m", "core.train_worker", job_id]

    worker_log_path = output_dir / WORKER_LOG_NAME
    log_handle = worker_log_path.open("a", encoding="utf-8", buffering=1)
    try:
        process = subprocess.Popen(
            worker_command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    finally:
        log_handle.close()
    store.update_train_job(job_id, process_id=process.pid)
    return get_train_job_with_progress(job_id)


def stop_train_job(job_id: str) -> dict:
    """用途：说明 训练任务、训练进度和模型包导出 中 `stop_train_job` 的职责和调用边界。
    入参：job_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

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
    """用途：说明 训练任务、训练进度和模型包导出 中 `_parse_datetime` 的职责和调用边界。
    入参：value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            pass
    return None


def _read_results_csv(job: dict) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_read_results_csv` 的职责和调用边界。
    入参：job，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    path = resolve_runtime_path(job["output_dir"], "训练输出目录") / "train" / "results.csv"
    if not path.exists():
        return [], {}
    rows: list[dict[str, Any]] = []
    # Ultralytics 的 results.csv 是训练进度和 ETA 的主事实来源，页面只消费解析后的摘要。
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {str(k).strip(): v for k, v in row.items() if k is not None}
            rows.append(cleaned)
    if not rows:
        return [], {}
    return rows, rows[-1]


def _float_or_none(value: Any) -> float | None:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_float_or_none` 的职责和调用边界。
    入参：value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _current_epoch_from_results(rows: list[dict[str, Any]], last: dict[str, Any]) -> int:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_current_epoch_from_results` 的职责和调用边界。
    入参：rows、last，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    epoch_value = _float_or_none(last.get("epoch"))
    if epoch_value is not None and epoch_value >= 0:
        return max(int(epoch_value), len(rows))
    return len(rows)


def _estimate_eta_seconds(job: dict, current: int, total: int, last: dict[str, Any]) -> int | None:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_estimate_eta_seconds` 的职责和调用边界。
    入参：job、current、total、last，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if job.get("status") in {"finished", "stopped", "failed"}:
        return None
    if current <= 0 or total <= 0 or current >= total:
        return None

    cumulative_time = _float_or_none(last.get("time"))
    if cumulative_time is not None and cumulative_time > 0:
        avg_epoch_seconds = cumulative_time / current
        return int(avg_epoch_seconds * (total - current))

    started = _parse_datetime(job.get("started_at"))
    if not started:
        return None
    elapsed = max(1, (datetime.now() - started).total_seconds())
    return int((elapsed / current) * (total - current))


def _available_model_files(job: dict) -> dict[str, str]:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_available_model_files` 的职责和调用边界。
    入参：job，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    weights_dir = resolve_runtime_path(job["output_dir"], "训练输出目录") / "train" / "weights"
    files: dict[str, str] = {}
    for name in ["best.pt", "last.pt"]:
        path = weights_dir / name
        if path.exists():
            files[name] = str(path)
    return files


def _worker_log_exists(job: dict) -> bool:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_worker_log_exists` 的职责和调用边界。
    入参：job，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    try:
        output_dir = resolve_runtime_path(job["output_dir"], "训练输出目录")
        log_path = output_dir / WORKER_LOG_NAME
        return log_path.exists() and log_path.stat().st_size > 0
    except Exception:
        return False


def _phase_text(job: dict, current_epoch: int) -> str:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_phase_text` 的职责和调用边界。
    入参：job、current_epoch，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    status = job.get("status")
    if status == "queued":
        return "训练准备中"
    if status == "running":
        if current_epoch > 0:
            return "训练中"
        started = _parse_datetime(job.get("started_at"))
        elapsed = (datetime.now() - started).total_seconds() if started else 0
        if elapsed > 120:
            return "训练初始化较慢，请稍候"
        if _worker_log_exists(job):
            return "正在加载模型/检查数据集"
        return "训练准备中"
    if status == "finished":
        return "已完成"
    if status == "stopped":
        return "已停止"
    if status == "failed":
        return "失败"
    return "等待中"


def _existing_package_for_job(train_job_id: str) -> dict[str, Any] | None:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_existing_package_for_job` 的职责和调用边界。
    入参：train_job_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    for package in store.list_model_packages():
        if package.get("train_job_id") == train_job_id:
            return package
    return None


def _default_package_name(job: dict[str, Any]) -> str:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_default_package_name` 的职责和调用边界。
    入参：job，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    project = store.get_project(job["project_id"])
    product_name = project.get("product_name") or project.get("name") or "通用检测模型"
    return f"{product_name}-{job.get('name') or job['id']}"


def get_train_job_with_progress(job_id: str, auto_package: bool = True) -> dict:
    """用途：说明 训练任务、训练进度和模型包导出 中 `get_train_job_with_progress` 的职责和调用边界。
    入参：job_id、auto_package，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    job = store.get_train_job(job_id)
    rows, last = _read_results_csv(job)
    total = int(job["params"].get("epochs") or job.get("progress", {}).get("total_epochs") or 0)
    current = _current_epoch_from_results(rows, last)
    percent = round((min(current, total) / total) * 100, 1) if total else 0
    eta_seconds = _estimate_eta_seconds(job, current, total, last)
    model_files = _available_model_files(job)
    job["progress"] = {
        "current_epoch": current,
        "total_epochs": total,
        "percent": percent,
        "eta_seconds": eta_seconds,
        "last_metrics": last,
        "series": rows[-200:],
        "model_files": model_files,
        "phase_text": _phase_text(job, current),
    }
    if auto_package and job.get("status") in {"finished", "stopped"} and model_files:
        try:
            job["model_package"] = ensure_model_package_for_job(job_id)
        except Exception as exc:
            job["model_package_error"] = str(exc)
    return job


def list_train_jobs_with_progress(project_id: str | None = None) -> list[dict]:
    """用途：说明 训练任务、训练进度和模型包导出 中 `list_train_jobs_with_progress` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    return [get_train_job_with_progress(job["id"]) for job in store.list_train_jobs(project_id)]


def ensure_model_package_for_job(job_id: str) -> dict[str, Any] | None:
    """用途：说明 训练任务、训练进度和模型包导出 中 `ensure_model_package_for_job` 的职责和调用边界。
    入参：job_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    job = get_train_job_with_progress(job_id, auto_package=False)
    if job.get("status") not in {"finished", "stopped"}:
        return None
    if not (job.get("progress", {}).get("model_files") or {}):
        return None
    # 模型包只在训练结束且已有权重文件后生成，避免把半成品 best.pt/last.pt 打包。
    existing = _existing_package_for_job(job_id)
    if existing:
        return existing
    return export_model_package(job_id, _default_package_name(job), auto_package=False)


def read_gpu_status() -> dict:
    """用途：说明 训练任务、训练进度和模型包导出 中 `read_gpu_status` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

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
    """用途：说明 训练任务、训练进度和模型包导出 中 `export_model_package` 的职责和调用边界。
    入参：train_job_id、name、auto_package，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    existing = _existing_package_for_job(train_job_id)
    if existing:
        return existing
    job = get_train_job_with_progress(train_job_id, auto_package=auto_package)
    model_files = job["progress"].get("model_files") or {}
    selected = model_files.get("best.pt") or model_files.get("last.pt")
    if not selected:
        raise FileNotFoundError("当前训练任务没有可用模型文件，不能生成模型目录。")
    dataset = store.get_dataset_version(job["dataset_version_id"])
    repair_dataset_artifacts(dataset["output_dir"])
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

    dataset_metadata = dataset.get("metadata") or {}
    recommended_imgsz = int(dataset_metadata.get("recommended_imgsz") or job["params"].get("recommended_imgsz") or job["params"].get("imgsz") or 1280)
    trained_imgsz = int(job["params"].get("imgsz") or recommended_imgsz)
    manifest = {
        "schema_version": "1.0",
        "package_id": package_id,
        "package_name": name,
        "default_weight": default_weight,
        "label_codes": dataset["label_codes"],
        "labels": label_rows,
        "image_scope": dataset_metadata.get("image_scope", "full_image"),
        "focus_region": {
            "id": dataset_metadata.get("focus_region_id"),
            "name": dataset_metadata.get("focus_region_name"),
            "rect_norm": dataset_metadata.get("focus_region_rect_norm"),
        } if dataset_metadata.get("focus_region_id") else None,
        "source_product": {"id": project["id"], "name": project["name"], "product_name": project.get("product_name", "")},
        "train_job_id": train_job_id,
        "dataset_version_id": dataset["id"],
        "recommended_imgsz": recommended_imgsz,
        "trained_imgsz": trained_imgsz,
        "recommended": {
            "imgsz": trained_imgsz,
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
