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
    settings = Settings(workspace_root="./var/workspace")
    assert settings.workspace_root.is_absolute()
    assert settings.workspace_root.name == "workspace"


def test_external_call_timeouts_have_sane_defaults() -> None:
    """Regression (PR2): every external dependency (OpenAI, Anthropic, Tavily)
    and the overall run must have a finite, non-zero deadline out of the box --
    a missing/zero default would silently restore the "hangs forever" bug."""
    settings = Settings()
    assert 0 < settings.openai_standard_timeout_seconds < settings.run_execution_timeout_seconds
    assert 0 < settings.openai_xhigh_timeout_seconds < settings.run_execution_timeout_seconds
    assert 0 < settings.anthropic_timeout_seconds < settings.run_execution_timeout_seconds
    assert 0 < settings.tavily_tool_timeout_seconds < settings.run_execution_timeout_seconds


def test_reconciliation_interval_has_a_sane_default() -> None:
    """Regression (PR3): periodic orphan reconciliation needs a finite,
    positive interval -- a missing/zero default would either never run or
    spin in a tight loop."""
    settings = Settings()
    assert settings.reconciliation_interval_seconds > 0
