from __future__ import annotations

import os
import sys
import traceback

from ultralytics import YOLO

from . import store
from .db import json_dumps
from .runtime_paths import repair_dataset_artifacts, resolve_runtime_path
from .utils import now_text


def _worker_count(params: dict) -> int:
    """用途：说明 训练任务、训练进度和模型包导出 中 `_worker_count` 的职责和调用边界。
    入参：params，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    raw = params.get("workers")
    if raw not in {None, "", "auto"}:
        return max(0, int(raw))
    # Apple MPS 的验证环境采用进程内加载，避免训练子进程再派生 DataLoader
    # 子进程造成启动不稳定；显式 workers 仍由调用方负责。
    if str(params.get("device") or "").strip().lower() == "mps":
        return 0
    # Packaged Windows executables are more reliable with in-process data
    # loading. It avoids PyInstaller/DataLoader child-process startup hangs.
    if os.name == "nt" or getattr(sys, "frozen", False):
        return 0
    return 4


def run(job_id: str) -> None:
    """用途：说明 训练任务、训练进度和模型包导出 中 `run` 的职责和调用边界。
    入参：job_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能创建训练目录、启动或停止训练子进程、读取训练日志和模型权重。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    try:
        job = store.get_train_job(job_id)
        dataset = store.get_dataset_version(job["dataset_version_id"])
        store.update_train_job(job_id, status="running", started_at=now_text(), log_text="模型训练已启动。")

        dataset_dir = resolve_runtime_path(dataset["output_dir"], "训练数据集目录", require_exists=True)
        repair_dataset_artifacts(dataset_dir)
        data_yaml = dataset_dir / "dataset.generated.yaml"
        if not data_yaml.exists():
            raise FileNotFoundError(
                "训练数据集配置不存在，请确认已复制 act_train_platform\\data\\datasets。"
                f" 原始目录={dataset['output_dir']}; 当前解析目录={dataset_dir}; 配置文件={data_yaml}"
            )

        output_dir = resolve_runtime_path(job["output_dir"], "训练输出目录", require_exists=False)
        output_dir.mkdir(parents=True, exist_ok=True)

        params = job["params"]
        train_kwargs = {
            "data": str(data_yaml),
            "project": str(output_dir),
            "name": "train",
            "exist_ok": True,
            "epochs": int(params.get("epochs") or 50),
            "imgsz": int(params.get("imgsz") or 1280),
            "batch": int(params.get("batch") or 8),
            "device": str(params.get("device") or "0").strip(),
            "workers": _worker_count(params),
            "patience": int(params.get("patience") or 30),
            "plots": True,
            "val": True,
            "save": True,
        }
        print(f"训练参数: {train_kwargs}", flush=True)
        model = YOLO(job["base_model_path"])
        result = model.train(**train_kwargs)
        store.update_train_job(
            job_id,
            status="finished",
            finished_at=now_text(),
            metrics_json=json_dumps({"result_type": type(result).__name__, "train_kwargs": train_kwargs}),
            log_text="模型训练完成，系统会自动整理到模型仓库。",
            process_id=0,
        )
    except Exception as exc:
        store.update_train_job(
            job_id,
            status="failed",
            finished_at=now_text(),
            log_text=f"{exc}\n{traceback.format_exc()}",
            process_id=0,
        )
        print(f"训练失败: {exc}", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    run(sys.argv[1])
