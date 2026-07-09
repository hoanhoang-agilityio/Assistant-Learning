from pathlib import Path

from core.config.settings import get_settings
from core.vfs.layout import VFS_SUBDIRS

RUN_WORKSPACE_PREFIX = "run_"
RUN_SUBDIRS = VFS_SUBDIRS


def run_workspace_name(run_id: str) -> str:
    return f"{RUN_WORKSPACE_PREFIX}{run_id}"


def run_workspace_path(run_id: str, workspace_root: Path | None = None) -> Path:
    settings = get_settings()
    root = (workspace_root or settings.workspace_root).resolve()
    return root / run_workspace_name(run_id)


def init_run_workspace(run_id: str, workspace_root: Path | None = None) -> Path:
    """Create `workspace/run_<id>/` folder tree and return its absolute path."""
    run_root = run_workspace_path(run_id, workspace_root=workspace_root)
    run_root.mkdir(parents=True, exist_ok=True)
    for subdir in VFS_SUBDIRS:
        (run_root / subdir).mkdir(parents=True, exist_ok=True)
    return run_root.resolve()
