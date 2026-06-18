from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import yaml

from .paths import DATA_ROOT


_DATA_MARKER = "act_train_platform/data/"


def _normalise_text_path(value: str) -> str:
    """用途：说明 运行路径解析和迁移兼容 中 `_normalise_text_path` 的职责和调用边界。
    入参：value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能解析运行目录、检查文件存在性或修复平台自有路径。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    return value.replace("\\", "/")


def _is_under(path: Path, root: Path) -> bool:
    """用途：说明 运行路径解析和迁移兼容 中 `_is_under` 的职责和调用边界。
    入参：path、root，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能解析运行目录、检查文件存在性或修复平台自有路径。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def map_to_current_data_root(value: str | Path | None) -> Path | None:
    """Map a stored platform data path to this installation's data root.

    Older records persisted absolute paths. After copying a packaged deployment
    to another machine or drive, those paths can point back to the development
    machine. If a stored path belongs to ``act_train_platform/data``, keep the
    suffix after that marker and resolve it under the current runtime
    ``DATA_ROOT``.

    If the stored path belongs to another installation's data directory, always
    prefer this installation's mapped path. This prevents copied source mirrors
    from accidentally reading files that still exist on the development machine.
    """
    if value in {None, ""}:
        return None
    raw = str(value)
    path = Path(raw)
    normalised = _normalise_text_path(raw)
    lowered = normalised.lower()
    marker_index = lowered.find(_DATA_MARKER)
    if marker_index < 0:
        return path

    relative_part = normalised[marker_index + len(_DATA_MARKER) :].lstrip("/")
    mapped = DATA_ROOT if not relative_part else DATA_ROOT / Path(*relative_part.split("/"))

    if not _is_under(path, DATA_ROOT):
        return mapped
    if path.exists():
        return path
    return mapped


def resolve_runtime_path(value: str | Path | None, label: str = "数据路径", require_exists: bool = False) -> Path:
    """用途：说明 运行路径解析和迁移兼容 中 `resolve_runtime_path` 的职责和调用边界。
    入参：value、label、require_exists，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能解析运行目录、检查文件存在性或修复平台自有路径。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    mapped = map_to_current_data_root(value)
    if mapped is None:
        raise FileNotFoundError(f"{label}为空")
    if require_exists and not mapped.exists():
        raise FileNotFoundError(f"{label}不存在。原始路径={value}; 当前机器解析路径={mapped}")
    return mapped


def runtime_path_exists(value: str | Path | None) -> bool:
    """用途：说明 运行路径解析和迁移兼容 中 `runtime_path_exists` 的职责和调用边界。
    入参：value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能解析运行目录、检查文件存在性或修复平台自有路径。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    mapped = map_to_current_data_root(value)
    return bool(mapped and mapped.exists())


def repair_runtime_paths_in_db(conn) -> dict[str, int]:
    """Repair safely mappable platform-owned paths in SQLite.

    Only paths whose target under the current ``DATA_ROOT`` exists are updated.
    External import paths are left alone.
    """
    repaired: dict[str, int] = {}
    targets: Iterable[tuple[str, str]] = [
        ("video_assets", "stored_path"),
        ("videos", "path"),
        ("frame_sets", "output_dir"),
        ("dataset_versions", "output_dir"),
        ("train_jobs", "output_dir"),
        ("model_packages", "package_dir"),
    ]
    for table, column in targets:
        try:
            rows = conn.execute(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
        except Exception:
            continue
        count = 0
        for row in rows:
            original = row[column]
            mapped = map_to_current_data_root(original)
            if mapped is None or not mapped.exists() or str(mapped) == str(original):
                continue
            conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (str(mapped), row["id"]))
            count += 1
        if count:
            repaired[f"{table}.{column}"] = count
    return repaired


def repair_dataset_artifacts(dataset_dir: str | Path) -> dict[str, int]:
    """Repair path metadata for one dataset directory on demand."""
    repaired = {"dataset_yaml": 0, "json": 0}
    root = resolve_runtime_path(dataset_dir, "训练数据集目录", require_exists=True)

    yaml_path = root / "dataset.generated.yaml"
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            mapped = map_to_current_data_root(data.get("path"))
            if mapped is not None and mapped.exists() and str(mapped) != str(data.get("path")):
                data["path"] = str(mapped)
                yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
                repaired["dataset_yaml"] += 1
        except Exception:
            pass

    json_path = root / "dataset_version.json"
    if json_path.exists():
        repaired["json"] += repair_json_metadata_file(json_path)
    return repaired


def repair_json_metadata_file(json_path: str | Path) -> int:
    """Repair platform-owned paths in a single JSON metadata file."""
    path = Path(json_path)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0
    if _DATA_MARKER not in _normalise_text_path(text).lower():
        return 0
    try:
        data = json.loads(text)
    except Exception:
        return 0
    new_data = _replace_platform_data_paths(data)
    if new_data == data:
        return 0
    path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1


def _replace_platform_data_paths(value):
    """用途：说明 运行路径解析和迁移兼容 中 `_replace_platform_data_paths` 的职责和调用边界。
    入参：value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能解析运行目录、检查文件存在性或修复平台自有路径。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if isinstance(value, str):
        mapped = map_to_current_data_root(value)
        if mapped is not None and _DATA_MARKER in _normalise_text_path(value).lower():
            return str(mapped)
        return value
    if isinstance(value, list):
        return [_replace_platform_data_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_platform_data_paths(item) for key, item in value.items()}
    return value
