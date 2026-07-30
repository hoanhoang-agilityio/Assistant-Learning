from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver

from core.adapters.mcp.fitness_client import FitnessMCPClient, configure_fitness_client
from core.adapters.mcp.mock_fitness import build_fake_fitness_client
from core.adapters.mcp.mock_tavily import build_mock_tavily_client
from core.adapters.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.adapters.observability.langfuse import reset_langfuse_client
from core.capabilities.fitness.planner import configure_fitness_planner
from core.capabilities.research.query_cache import reset_tavily_search_cache
from core.capabilities.research.research_agent import configure_research_agent
from core.config.settings import get_settings
from core.orchestration.agents.intent_judge import configure_user_intent_judge
from core.orchestration.agents.supervisor_router_judge import configure_supervisor_routing_judge
from core.orchestration.agents.topic_scope_judge import configure_topic_scope_judge
from core.orchestration.graph.run import create_initial_state
from core.orchestration.state import OrchestrationState
from core.shared.profile.extraction import configure_profile_extractor
from tests.helpers.classification import (
    default_topic_scope_judge,
    default_user_intent_judge,
)
from tests.helpers.fitness import default_structured_workout
from tests.helpers.research import research_agent_override
from tests.helpers.routing import default_supervisor_routing_judge


@pytest.fixture(autouse=True)
def reset_fitness_client() -> None:
    configure_fitness_client(None)
    yield
    configure_fitness_client(None)


@pytest.fixture
def fitness_client() -> FitnessMCPClient:
    """Fresh in-memory fake Fitness MCP client -- request by name to seed guideline
    documents or template state before calling production code (mirrors
    mock_tavily_client's not-autouse, returns-the-client shape)."""
    client = build_fake_fitness_client()
    configure_fitness_client(client)
    return client


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
def reset_topic_scope_judge() -> None:
    configure_topic_scope_judge(default_topic_scope_judge)
    yield
    configure_topic_scope_judge(None)


@pytest.fixture(autouse=True)
def reset_user_intent_judge() -> None:
    configure_user_intent_judge(default_user_intent_judge)
    yield
    configure_user_intent_judge(None)


@pytest.fixture(autouse=True)
def reset_supervisor_routing_judge() -> None:
    configure_supervisor_routing_judge(default_supervisor_routing_judge)
    yield
    configure_supervisor_routing_judge(None)


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


@pytest.fixture(autouse=True)
def reset_tavily_search_cache_fixture() -> None:
    reset_tavily_search_cache()
    yield
    reset_tavily_search_cache()


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
    # settings.verification_use_real_ragas defaults to True in production, but
    # run_golden_case() reads it unconditionally -- without this, any test
    # touching golden cases (e.g. test_golden_cases_meet_faithfulness_threshold)
    # silently makes real, billed OpenAI calls via the real Ragas SDK instead of
    # the free heuristic. Tests that specifically want the real SDK path
    # (test_real_ragas_sanity_check_on_clean_golden_cases) already monkeypatch
    # this back to True themselves.
    monkeypatch.setenv("VERIFICATION_USE_REAL_RAGAS", "false")
    # Same reasoning, for the Phase 3 production gate: this repo's local .env
    # sets VERIFICATION_PRODUCTION_USE_REAL_RAGAS=true (2026-07-30), so without
    # this override every test that runs verification/executor.py (e2e,
    # integration) would silently make real Ragas calls too. Tests exercising
    # the real path explicitly (tests/test_verification_faithfulness_dispatch.py)
    # inject their own AIRateLimiter and monkeypatch the scorer -- they don't
    # depend on this setting being True.
    monkeypatch.setenv("VERIFICATION_PRODUCTION_USE_REAL_RAGAS", "false")
    get_settings.cache_clear()
    reset_langfuse_client()
    yield
    get_settings.cache_clear()
    reset_langfuse_client()


@pytest.fixture
def memory_checkpointer():
    return MemorySaver()
