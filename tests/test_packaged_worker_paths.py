"""冻结训练沿用同一EXE，把第三方库的相对写入限制到该任务的数据目录。"""
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from core.training import training_ops


@pytest.mark.parametrize("frozen,separated", [(True, True), (True, False), (False, True)])
def test_worker_working_directory_preserves_source_mode(tmp_path, monkeypatch, frozen, separated):
    """只改变新布局冻结worker的工作目录，源码模块启动与旧包行为保持不变。"""
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    if separated:
        monkeypatch.setenv("ACT_DEPLOYMENT_ROOT", str(tmp_path))
    else:
        monkeypatch.delenv("ACT_DEPLOYMENT_ROOT", raising=False)
    monkeypatch.setattr(training_ops, "RUNS_DIR", tmp_path / "data/runs")
    monkeypatch.setattr(training_ops, "new_id", lambda prefix: "job-test")
    monkeypatch.setattr(training_ops, "repair_dataset_artifacts", lambda path: None)
    monkeypatch.setattr(training_ops.store, "get_dataset_version", lambda key: {"output_dir": str(tmp_path), "metadata": {}})
    monkeypatch.setattr(training_ops.store, "save_train_job", lambda value: None)
    monkeypatch.setattr(training_ops.store, "update_train_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(training_ops, "get_train_job_with_progress", lambda key: {"id": key})
    calls = []
    monkeypatch.setattr(training_ops.subprocess, "Popen", lambda command, **kwargs: (calls.append((command, kwargs)) or SimpleNamespace(pid=123)))
    training_ops.create_train_job("project", "dataset", "test", str(tmp_path / "local.pt"), {"epochs": 1})
    command, options = calls[0]
    expected = tmp_path / "data/runs/project/job-test" if frozen else training_ops.PROJECT_ROOT
    assert Path(options["cwd"]) == expected
    assert command == ([sys.executable, "--train-worker", "job-test"] if frozen else [sys.executable, "-m", "core.train_worker", "job-test"])
