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
    raw = params.get("workers")
    if raw not in {None, "", "auto"}:
        return max(0, int(raw))
    # Packaged Windows executables are more reliable with in-process data
    # loading. It avoids PyInstaller/DataLoader child-process startup hangs.
    if os.name == "nt" or getattr(sys, "frozen", False):
        return 0
    return 4


def run(job_id: str) -> None:
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
            "device": str(params.get("device") or "0"),
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
