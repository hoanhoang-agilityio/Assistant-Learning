from pathlib import Path

from core.config.settings import Settings, get_settings


class VFS:
    """Path-safe virtual file system rooted at a workspace directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @classmethod
    def from_workspace_root(
        cls,
        workspace_root: Path | None = None,
        settings: Settings | None = None,
    ) -> "VFS":
        resolved_settings = settings or get_settings()
        root = workspace_root or resolved_settings.workspace_root
        return cls(root=root.resolve())

    @classmethod
    def for_run(cls, run_workspace_path: Path) -> "VFS":
        return cls(root=run_workspace_path.resolve())

    @property
    def root(self) -> Path:
        return self._root

    def read(self, path: str) -> str:
        target = self._resolve_path(path)
        return target.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def exists(self, path: str) -> bool:
        return self._resolve_path(path).exists()

    def append(self, path: str, content: str) -> None:
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)

    def _resolve_path(self, path: str) -> Path:
        normalized = path.strip().replace("\\", "/").lstrip("/")
        if not normalized:
            raise ValueError("VFS path must not be empty")
        target = (self._root / normalized).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError(f"Path escapes workspace root: {path}")
        return target
