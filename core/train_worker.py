from __future__ import annotations

import sys
import traceback
from pathlib import Path

from ultralytics import YOLO

from . import store
from .db import json_dumps
from .utils import now_text


def run(job_id: str) -> None:
    try:
        job = store.get_train_job(job_id)
        dataset = store.get_dataset_version(job["dataset_version_id"])
        store.update_train_job(job_id, status="running", started_at=now_text(), log_text="模型训练已启动。")
        data_yaml = Path(dataset["output_dir"]) / "dataset.generated.yaml"
        params = job["params"]
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
            "save": True,
        }
        model = YOLO(job["base_model_path"])
        result = model.train(**train_kwargs)
        store.update_train_job(
            job_id,
            status="finished",
            finished_at=now_text(),
            metrics_json=json_dumps({"result_type": type(result).__name__, "train_kwargs": train_kwargs}),
            log_text="模型训练完成，可到模型仓库生成模型目录。",
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


if __name__ == "__main__":
    run(sys.argv[1])
