from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import yaml

from .paths import DATA_ROOT


_DATA_MARKER = "act_train_platform/data/"


def _normalise_text_path(value: str) -> str:
    return value.replace("\\", "/")


def map_to_current_data_root(value: str | Path | None) -> Path | None:
    """Map a stored platform data path to this installation's data root.

    The platform used to persist absolute paths. After a packaged deployment is
    copied to another machine or drive, those paths can point back to the
    development machine. If the stored path contains the platform data marker,
    keep the part after ``act_train_platform/data`` and resolve it under the
    current runtime DATA_ROOT.
    """
    if value in {None, ""}:
        return None
    raw = str(value)
    path = Path(raw)
    if path.exists():
        return path

    normalised = _normalise_text_path(raw)
    lowered = normalised.lower()
    marker_index = lowered.find(_DATA_MARKER)
    if marker_index < 0:
        return path

    relative_part = normalised[marker_index + len(_DATA_MARKER) :].lstrip("/")
    if not relative_part:
        return DATA_ROOT
    return DATA_ROOT / Path(*relative_part.split("/"))


def resolve_runtime_path(value: str | Path | None, label: str = "数据路径", require_exists: bool = False) -> Path:
    mapped = map_to_current_data_root(value)
    if mapped is None:
        raise FileNotFoundError(f"{label}为空")
    if require_exists and not mapped.exists():
        raise FileNotFoundError(f"{label}不存在: 原始路径={value}; 当前机器解析路径={mapped}")
    return mapped


def runtime_path_exists(value: str | Path | None) -> bool:
    mapped = map_to_current_data_root(value)
    return bool(mapped and mapped.exists())


def repair_runtime_paths_in_db(conn) -> dict[str, int]:
    """Repair safely mappable platform-owned paths in SQLite.

    Only paths that currently do not exist and whose mapped target under the
    current DATA_ROOT exists are updated. External import paths are left alone.
    """
    repaired: dict[str, int] = {}
    targets: Iterable[tuple[str, str]] = [
        ("video_assets", "stored_path"),
        ("videos", "path"),
        ("frame_sets", "output_dir"),
        ("frames", "path"),
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
            if mapped is None:
                continue
            original_path = Path(str(original))
            if original_path.exists() or not mapped.exists() or str(mapped) == str(original):
                continue
            conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (str(mapped), row["id"]))
            count += 1
        if count:
            repaired[f"{table}.{column}"] = count
    return repaired


def repair_dataset_metadata_files() -> dict[str, int]:
    repaired = {"dataset_yaml": 0, "json": 0}
    if not DATA_ROOT.exists():
        return repaired

    for yaml_path in DATA_ROOT.glob("datasets/**/dataset.generated.yaml"):
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        mapped = map_to_current_data_root(data.get("path"))
        if mapped is None or str(mapped) == str(data.get("path")):
            continue
        if not mapped.exists():
            continue
        data["path"] = str(mapped)
        yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        repaired["dataset_yaml"] += 1

    for json_path in DATA_ROOT.glob("**/*.json"):
        if json_path.name not in {"dataset_version.json", "model_manifest.json", "train_report.json"}:
            continue
        try:
            text = json_path.read_text(encoding="utf-8")
        except Exception:
            continue
        normalised = _normalise_text_path(text)
        lowered = normalised.lower()
        marker_index = lowered.find(_DATA_MARKER)
        if marker_index < 0:
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        new_text = _replace_platform_data_paths(data)
        if new_text is None:
            continue
        json_path.write_text(json.dumps(new_text, ensure_ascii=False, indent=2), encoding="utf-8")
        repaired["json"] += 1
    return repaired


def _replace_platform_data_paths(value):
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
