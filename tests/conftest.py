from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.graph.checkpointer import create_memory_checkpointer
from core.graph.run import create_initial_state
from core.mcp.mock_tavily import build_mock_tavily_client
from core.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.observability.langfuse import reset_langfuse_client
from core.profile.extraction import configure_profile_extractor
from core.subgraphs.fitness.planner import configure_fitness_planner
from core.subgraphs.fitness.template_registry import configure_template_registry
from core.subgraphs.planning.planning_agent import configure_planning_agent
from core.subgraphs.planning.utils import build_default_execution_plan
from core.subgraphs.research.research_agent import configure_research_agent
from tests.helpers.fitness import default_structured_workout
from tests.helpers.research import research_agent_override


@pytest.fixture(autouse=True)
def isolated_template_registry(tmp_path: Path) -> None:
    """Keep workout template cache out of src/workspace/templates during tests."""
    configure_template_registry(tmp_path / "template_registry")
    yield
    configure_template_registry(None)


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
def reset_profile_extractor() -> None:
    configure_profile_extractor(None)
    yield
    configure_profile_extractor(None)


@pytest.fixture(autouse=True)
def reset_planning_agent() -> None:
    configure_planning_agent(lambda **kwargs: build_default_execution_plan(kwargs.get("profile")))
    yield
    configure_planning_agent(None)


@pytest.fixture(autouse=True)
def reset_fitness_planner() -> None:
    configure_fitness_planner(
        lambda **kwargs: default_structured_workout(
            profile=kwargs.get("profile"),
            constraints=kwargs.get("constraints"),
        )
    )
    yield
    configure_fitness_planner(None)


@pytest.fixture(autouse=True)
def reset_research_agent() -> None:
    configure_research_agent(research_agent_override)
    yield
    configure_research_agent(None)


@pytest.fixture(autouse=True)
def reset_tavily_client() -> None:
    configure_tavily_client(None)
    yield
    configure_tavily_client(None)


@pytest.fixture
def mock_tavily_client() -> TavilyMCPClient:
    client = build_mock_tavily_client()
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
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    reset_langfuse_client()
    yield
    get_settings.cache_clear()
    reset_langfuse_client()


@pytest.fixture
def memory_checkpointer():
    return create_memory_checkpointer()
