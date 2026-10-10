"""仅供数据集生成/导入使用的短名称；不改变客户源文件或全局路径规则。"""
from __future__ import annotations

import json
import os
from pathlib import Path


def validate_target(root: Path) -> None:
    """为图片/标签及临时元数据预留Windows长度预算，失败发生在创建目录之前。"""
    target = str(root.resolve() / "images/train/img_00000001.jpeg")
    if os.name == "nt" and len(target.encode("utf-16-le")) // 2 > 240:
        raise ValueError("数据集目标路径过长，请在较短的数据根目录操作；未写入数据：" + str(root))


def windows_read_path(path: Path) -> Path:
    """局部启用Windows Unicode长路径读取；不依赖系统策略，不用于输出命名。"""
    if os.name != "nt":
        return path
    value = str(path.resolve())
    if value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


class DatasetFilenames:
    """在一次数据集生成内分配唯一短stem，来源信息另存而不叠加到文件名。"""

    def __init__(self, root: Path):
        validate_target(root)
        self.root = root
        self.counter = 0
        self.files: list[dict] = []

    def allocate(self, split: str, suffix: str) -> tuple[Path, Path]:
        """图片和标签共用stem；即使已有同stem不同扩展名也不覆盖。"""
        if split not in {"train", "val", "test"}:
            raise ValueError("不支持的数据集划分：" + str(split))
        suffix = suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}:
            raise ValueError("不支持的图片扩展名：" + suffix)
        while True:
            self.counter += 1
            stem = f"img_{self.counter:08d}"
            image = self.root / "images" / split / (stem + suffix)
            label = self.root / "labels" / split / (stem + ".txt")
            if not label.exists() and not any(image.parent.glob(stem + ".*")):
                return image, label

    def record(self, image: Path, split: str, source_id: str, relative_path: str) -> None:
        """只记录成功输出的对应关系，原始长名称不再用于目标路径。"""
        self.files.append({"image": image.relative_to(self.root).as_posix(), "split": split,
                           "source_id": source_id, "source_relative_path": relative_path})

    def save(self) -> None:
        """映射在数据集成功登记前落盘；中断不能留下半个JSON冒充完整映射。"""
        target = self.root / "filename_map.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"version": 1, "files": self.files}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
