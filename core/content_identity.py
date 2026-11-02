"""素材内容身份：所有入口使用同一种SHA256，兼容未登记身份的旧帧。"""
import hashlib
from pathlib import Path


def file_sha256(path):
    """分块读入而非整图累积；缺失素材应明确报错，不能跳过去重。"""
    try:
        digest=hashlib.sha256()
        with Path(path).open("rb") as source:
            for block in iter(lambda: source.read(1024*1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ValueError("无法读取原图内容以校验数据划分") from exc


def frame_sha256(row, config):
    """优先读取内容寻址资产及导入身份；旧库只读补算，不改用户数据库。"""
    return (row.get("sha256") or config.get("source_hashes",{}).get(row["frame_id"])
            or config.get("source_images",{}).get(row["frame_id"],{}).get("sha256")
            or file_sha256(row["frame_path"]))
