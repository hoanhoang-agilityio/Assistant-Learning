import pytest

from core.config.settings import Settings


def test_checkpointer_dsn_from_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        database_url=None,
        postgres_user="user",
        postgres_password="pass",
        postgres_host="db",
        postgres_port=5433,
        postgres_db="testdb",
    )
    assert settings.checkpointer_dsn == "postgresql://user:pass@db:5433/testdb"


def test_workspace_root_resolves() -> None:
    settings = Settings(workspace_root="./src/workspace")
    assert settings.workspace_root.is_absolute()
    assert settings.workspace_root.name == "workspace"
