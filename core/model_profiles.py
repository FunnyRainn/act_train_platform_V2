"""受管基础权重准备：唯一公开目录来自共同合同，固定来源、校验后才可训练。"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from core.paths import DATA_ROOT
from core.task_contract import MODEL_PROFILES, ULTRALYTICS_TASKS, model_profile

CACHE = DATA_ROOT / "base_models"
RELEASE = "v8.4.0"
# 2026-09-20经48读取官方release API得到的不可变资产大小与SHA256。
# 把摘要随目录锁定，运行期不依赖GitHub匿名API额度，更不能在限流时降级校验。
ASSETS = {
    "yolo11m-seg.pt": (45400152, "eb9a06f63e2206c35d68d839b08c362429ebecf933ad54c1ad68b2fd001c17cf"),
    "yolo11m.pt": (40684120, "d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95"),
    "yolo26l-seg.pt": (63700037, "636024306410afa1732692322fba57d22ea2b1c2f07613fcee131a93d7dd380c"),
    "yolo26l-sem.pt": (36167967, "e4dfbd78b4bd54cbcb984aef035248af7e2559d227dc8fbf41b4f1864bc2cd21"),
    "yolo26l.pt": (53211173, "9fe3c544f2b19bebad7ea41e76d7ad3d88b7c2f10d11d24430c5311f6b32db26"),
    "yolo26m-seg.pt": (54750385, "16b636f04e8fb6a325b3370f22dc5e5535ff473e384f4d041fd28d788f6ee9f5"),
    "yolo26m-sem.pt": (28924971, "3de52574cf1b18e38d32d9e51fc57135abc4f8dda37ff13ccbf44dcf99986233"),
    "yolo26m.pt": (44255705, "401cea9ab23ad19246ff7744859816bc599f350e93c9dd30367b6f0a0745d0b7"),
    "yolo26s-seg.pt": (23467933, "3da1d83e31caec96f9300eb4064f4f62882c133c7c264d63dfe61a7c197837a4"),
    "yolo26s-sem.pt": (13252403, "bc3e2152329831303de83e1af91d4b57d547e8794de8bb6edb1f2a622d1d5435"),
    "yolo26s.pt": (20422725, "646f8bc3fe0a656803d95c294f7852321748cb29d13466a1af8862e2db384a1b"),
}
_lock = threading.Lock()
_states: dict[str, dict] = {}


def source_asset(profile: dict) -> str:
    """固定受支持来源；未知ID不构造任意URL，不回退到latest。"""
    row = model_profile(profile["id"], profile["task_type"])
    stem = {"small": "yolo26s", "medium": "yolo26m", "large": "yolo26l", "general": "yolo11m"}[row["size"]]
    suffix = {"detect": "", "instance_segment": "-seg", "semantic_segment": "-sem"}[row["task_type"]]
    return stem + suffix + ".pt"


def file_digest(path: Path) -> str:
    """分块校验，避免为大模型额外分配整文件内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_model(profile: dict) -> Path | None:
    """已有缓存必须同时具备完整收据和匹配摘要，残缺文件不能直接使用。"""
    path = CACHE / (profile["name"] + ".pt")
    receipt = path.with_suffix(".json")
    if not path.exists() and not receipt.exists():
        return None
    if not path.is_file() or not receipt.is_file():
        raise ValueError("基础模型缓存不完整，请重新准备该型号")
    info = json.loads(receipt.read_text(encoding="utf-8"))
    expected_size, expected_digest = ASSETS[source_asset(profile)]
    if (info.get("profile_id") != profile["id"] or info.get("sha256") != expected_digest
            or path.stat().st_size != expected_size or expected_digest != file_digest(path)):
        raise ValueError("基础模型缓存校验失败，禁止继续训练")
    return path


def profile_status(task: str | None = None) -> list[dict]:
    """页面查询不下载、不加载GPU；就绪意味着文件与校验收据都存在。"""
    rows = []
    for row in MODEL_PROFILES:
        if task and row["task_type"] != task:
            continue
        path = CACHE / (row["name"] + ".pt")
        with _lock:
            state = dict(_states.get(row["id"], {}))
        if not state:
            state = {"status": "cached" if path.is_file() and path.with_suffix(".json").is_file() else "not_prepared"}
        rows.append(dict(row, **state))
    return rows


def prepare_model(profile: dict) -> Path:
    """下载来自固定官方发行版，核对发布摘要、大小和实际任务后原子发布缓存。"""
    profile = model_profile(profile["id"], profile["task_type"])
    with _lock:
        if _states.get(profile["id"], {}).get("status") == "preparing":
            raise ValueError("此型号正在准备，请稍后重试")
        _states[profile["id"]] = {"status": "preparing"}
    partial = CACHE / (profile["name"] + ".download.pt")
    try:
        existing = cached_model(profile)
        if existing:
            result = existing
        else:
            CACHE.mkdir(parents=True, exist_ok=True)
            asset = source_asset(profile)
            expected_size, expected = ASSETS[asset]
            url = f"https://github.com/ultralytics/assets/releases/download/{RELEASE}/{asset}"
            with urlopen(Request(url, headers={"User-Agent": "Pie-model-manager"}), timeout=60) as response, partial.open("wb") as target:
                count = 0
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > expected_size:
                        raise ValueError("基础模型下载超出官方声明大小")
                    target.write(block)
            digest = file_digest(partial)
            if count != expected_size or digest != expected:
                raise ValueError("基础模型下载大小或SHA256不匹配")
            # 仅固定官方来源的受管文件通过摘要后才反序列化；用户本地模型另有高级入口。
            from ultralytics import YOLO
            model = YOLO(str(partial))
            if model.task != ULTRALYTICS_TASKS[profile["task_type"]]:
                raise ValueError("基础模型实际任务与型号目录不匹配")
            del model
            result = CACHE / (profile["name"] + ".pt")
            partial.replace(result)
            result.with_suffix(".json").write_text(json.dumps({"profile_id": profile["id"], "sha256": digest,
                "release": RELEASE, "asset": asset, "source": url, "size": count}, indent=2), encoding="utf-8")
        with _lock:
            _states[profile["id"]] = {"status": "ready"}
        return result
    except Exception as exc:
        with _lock:
            _states[profile["id"]] = {"status": "failed", "error": str(exc)}
        raise
    finally:
        # 仅回收本函数确定生成的可重建临时下载；不删除旧模型或未知目录。
        partial.unlink(missing_ok=True)
