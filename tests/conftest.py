from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.graph.checkpointer import create_memory_checkpointer
from core.graph.run import create_initial_state
from core.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.observability.langfuse import reset_langfuse_client


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
    }


@pytest.fixture(autouse=True)
def reset_tavily_client() -> None:
    configure_tavily_client(None)
    yield
    configure_tavily_client(None)


@pytest.fixture
def mock_tavily_client() -> TavilyMCPClient:
    def search(query: str) -> dict[str, Any]:
        return {
            "results": [
                {
                    "title": f"Evidence for {query}",
                    "url": "https://example.edu/fitness-training",
                    "content": "hypertrophy training evidence for strength programming",
                    "score": 0.92,
                },
                {
                    "title": "Generic page",
                    "url": "https://example.com/page",
                    "content": "unrelated content",
                    "score": 0.2,
                },
            ]
        }

    def extract(urls: list[str]) -> dict[str, Any]:
        return {
            "results": [{"url": url, "raw_content": f"Document body for {url}"} for url in urls]
        }

    client = TavilyMCPClient(search=search, extract=extract)
    configure_tavily_client(client)
    return client


@pytest.fixture
def orchestration_state(
    workspace_root: Path,
    complete_profile: dict[str, Any],
) -> OrchestrationState:
    return create_initial_state(
        run_id="e2e-run",
        thread_id="e2e-thread",
        query="I want a 4-day training plan to lose weight with strength training.",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )


@pytest.fixture(autouse=True)
def disable_langfuse_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()
    reset_langfuse_client()
    yield
    get_settings.cache_clear()
    reset_langfuse_client()


@pytest.fixture
def memory_checkpointer():
    return create_memory_checkpointer()
