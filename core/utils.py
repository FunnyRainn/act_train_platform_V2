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
    """用途：说明 通用工具函数 中 `now_text` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id(prefix: str) -> str:
    """用途：说明 通用工具函数 中 `new_id` 的职责和调用边界。
    入参：prefix，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def safe_name(name: str, default: str = "item") -> str:
    """用途：说明 通用工具函数 中 `safe_name` 的职责和调用边界。
    入参：name、default，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    text = re.sub(r"[^\w\-.]+", "_", name.strip(), flags=re.UNICODE)
    text = text.strip("._")
    return text or default


def list_video_files(root: Path) -> list[Path]:
    """用途：说明 通用工具函数 中 `list_video_files` 的职责和调用边界。
    入参：root，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if not root.exists():
        return []
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
    files.sort()
    return files


def clean_dir(path: Path) -> None:
    """用途：说明 通用工具函数 中 `clean_dir` 的职责和调用边界。
    入参：path，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    """用途：说明 通用工具函数 中 `copy_file` 的职责和调用边界。
    入参：src、dst，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def normalize_bbox(box: dict) -> tuple[float, float, float, float]:
    """用途：说明 通用工具函数 中 `normalize_bbox` 的职责和调用边界。
    入参：box，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

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
    """用途：说明 通用工具函数 中 `split_by_ratio` 的职责和调用边界。
    入参：items、train_ratio、val_ratio，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    train_count = max(1, int(len(items) * train_ratio)) if items else 0
    val_count = max(1, int(len(items) * val_ratio)) if len(items) > 2 else 0
    train = items[:train_count]
    val = items[train_count : train_count + val_count]
    test = items[train_count + val_count :]
    if not val and test:
        val = [test.pop(0)]
    return train, val, test


def unique_keep_order(values: Iterable[str]) -> list[str]:
    """用途：说明 通用工具函数 中 `unique_keep_order` 的职责和调用边界。
    入参：values，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取配置、访问文件系统或调用下层业务模块。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
