from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable


VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def safe_name(name: str, default: str = "item") -> str:
    text = re.sub(r"[^\w\-.]+", "_", name.strip(), flags=re.UNICODE)
    text = text.strip("._")
    return text or default


def list_video_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
    files.sort()
    return files


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def normalize_bbox(box: dict) -> tuple[float, float, float, float]:
    x = max(0.0, min(1.0, float(box["x"])))
    y = max(0.0, min(1.0, float(box["y"])))
    w = max(0.0, min(1.0, float(box["w"])))
    h = max(0.0, min(1.0, float(box["h"])))
    if x + w > 1:
        w = 1 - x
    if y + h > 1:
        h = 1 - y
    return x, y, w, h


def split_by_ratio(items: list[str], train_ratio: float, val_ratio: float) -> tuple[list[str], list[str], list[str]]:
    train_count = max(1, int(len(items) * train_ratio)) if items else 0
    val_count = max(1, int(len(items) * val_ratio)) if len(items) > 2 else 0
    train = items[:train_count]
    val = items[train_count : train_count + val_count]
    test = items[train_count + val_count :]
    if not val and test:
        val = [test.pop(0)]
    return train, val, test


def unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
