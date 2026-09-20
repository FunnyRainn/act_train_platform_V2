"""按角色管理新训练产物；旧任务没有清单时继续识别历史文件名。"""
from __future__ import annotations

import json
from pathlib import Path

from core.task_contract import package_weight_path

MANIFEST = "model_artifacts.json"


def artifact_paths(output_dir: Path) -> dict[str, Path]:
    """清单存在则严格遵守，不在错误清单时回退扫描其他权重。"""
    manifest = output_dir / MANIFEST
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or set(data.get("weights", {})) != {"best", "last"}:
            raise ValueError("训练产物清单版本或角色错误")
        paths = {role: package_weight_path(output_dir, name) for role, name in data["weights"].items()}
    else:
        paths = {role: output_dir / "train" / "weights" / f"{role}.pt" for role in ("best", "last")}
    return {role: path for role, path in paths.items() if path.is_file()}


def configure_artifacts(trainer, output_dir: Path, model_name: str) -> None:
    """利用官方回调设置检查点名称，不修改第三方代码或训练后复制双份权重。"""
    weights = {}
    for role in ("best", "last"):
        path = Path(trainer.wdir) / f"{model_name}_{role.title()}.pt"
        if not path.resolve().is_relative_to(output_dir.resolve()):
            raise ValueError("训练产物越出任务目录")
        setattr(trainer, role, path)
        weights[role] = path.relative_to(output_dir).as_posix()
    manifest = output_dir / MANIFEST
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema_version": 1, "model_name": model_name, "weights": weights}, indent=2), encoding="utf-8")
    temporary.replace(manifest)
