"""不下载模型的目录、准备错误及产物清单回归。"""
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from core import model_profiles as profiles
from core.task_contract import model_profile
from core.training.model_artifacts import artifact_paths, configure_artifacts


def test_source_and_cache_integrity(tmp_path):
    row = model_profile(None, "instance_segment")
    assert profiles.source_asset(row) == "yolo26s-seg.pt"
    with patch.object(profiles, "CACHE", tmp_path), patch.dict(profiles.ASSETS,
            {"yolo26s-seg.pt": (11, hashlib.sha256(b"test-weight").hexdigest())}):
        assert profiles.cached_model(row) is None
        path = tmp_path / "PieV2S_Seg.pt"
        path.write_bytes(b"test-weight")
        with pytest.raises(ValueError, match="不完整"):
            profiles.cached_model(row)
        path.with_suffix(".json").write_text(json.dumps({"profile_id": row["id"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
        assert profiles.cached_model(row) == path
        path.write_bytes(b"modified")
        with pytest.raises(ValueError, match="校验失败"):
            profiles.cached_model(row)


def test_artifact_roles_and_legacy(tmp_path):
    weights = tmp_path / "train/weights"
    weights.mkdir(parents=True)
    (weights / "best.pt").write_bytes(b"legacy")
    assert artifact_paths(tmp_path)["best"].name == "best.pt"
    trainer = SimpleNamespace(wdir=weights)
    configure_artifacts(trainer, tmp_path, "PieV2S_Seg")
    assert artifact_paths(tmp_path) == {}  # 有清单后绝不误选残留旧文件。
    trainer.best.write_bytes(b"new")
    assert artifact_paths(tmp_path) == {"best": trainer.best}
    assert trainer.last.name == "PieV2S_Seg_Last.pt"


def test_artifact_escape_rejected(tmp_path):
    (tmp_path / "model_artifacts.json").write_text(json.dumps({"schema_version": 1,
        "weights": {"best": "../wrong.pt", "last": "last.pt"}}))
    with pytest.raises(ValueError, match="相对路径"):
        artifact_paths(tmp_path)


def test_download_failure_not_replaced(tmp_path):
    row = model_profile("PieV2L", "detect")
    with patch.object(profiles, "CACHE", tmp_path), patch.object(profiles, "urlopen", side_effect=TimeoutError("offline")):
        with pytest.raises(TimeoutError):
            profiles.prepare_model(row)
        result = next(item for item in profiles.profile_status("detect") if item["id"] == row["id"])
        assert result["status"] == "failed"
        assert not list(tmp_path.glob("*.pt"))
