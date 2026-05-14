from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
ASSETS_DIR = DATA_ROOT / "assets"
UPLOADS_DIR = DATA_ROOT / "uploads"
IMPORTS_DIR = DATA_ROOT / "imports"
FRAMES_DIR = DATA_ROOT / "frames"
DATASETS_DIR = DATA_ROOT / "datasets"
RUNS_DIR = DATA_ROOT / "runs"
PACKAGES_DIR = DATA_ROOT / "packages"
PRELABELS_DIR = DATA_ROOT / "prelabels"
DB_PATH = DATA_ROOT / "act_train_platform.sqlite3"


def ensure_runtime_dirs() -> None:
    """Create all runtime directories used by the platform."""
    for path in [
        DATA_ROOT,
        ASSETS_DIR,
        UPLOADS_DIR,
        IMPORTS_DIR,
        FRAMES_DIR,
        DATASETS_DIR,
        RUNS_DIR,
        PACKAGES_DIR,
        PRELABELS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
