from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from core.capabilities.research.utils import extract_tavily_data, search_tavily_data
from core.config.settings import get_settings
from core.mcp.tavily_client import TAVILY_EXTRACT_TOOL, TAVILY_SEARCH_TOOL, TavilyMCPClient
from core.observability.langfuse import reset_langfuse_client
from core.observability.tracing import reset_trace_run_id, set_trace_run_id
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.graph.builder import build_graph


class _RecordingSpan:
    def update(self, **_kwargs: object) -> None:
        return None


@pytest.fixture
def langfuse_span_recorder(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Re-enable Langfuse in tests and record opened span names."""
    span_names: list[str] = []

    @contextmanager
    def record_span(**kwargs: object) -> Iterator[_RecordingSpan]:
        span_names.append(str(kwargs.get("name", "")))
        yield _RecordingSpan()

    mock_client = MagicMock()
    mock_client.create_trace_id.return_value = "trace-integration"
    mock_client.start_as_current_span.side_effect = record_span

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
    get_settings.cache_clear()
    reset_langfuse_client()

    with (
        patch("core.observability.langfuse.verify_langfuse_credentials", return_value=(True, None)),
        patch("core.observability.langfuse.get_langfuse_client", return_value=mock_client),
        patch("core.observability.langfuse.is_langfuse_enabled", return_value=True),
        patch("core.observability.langfuse.CallbackHandler", return_value=MagicMock()),
    ):
        yield span_names

    get_settings.cache_clear()
    reset_langfuse_client()


def test_langfuse_subgraph_hierarchy_during_happy_path(
    orchestration_state: OrchestrationState,
    memory_checkpointer,
    mock_tavily_client: TavilyMCPClient,
    langfuse_span_recorder: list[str],
) -> None:
    del mock_tavily_client
    graph = build_graph(checkpointer=memory_checkpointer)
    config = {"configurable": {"thread_id": orchestration_state["thread_id"]}}

    graph.invoke(orchestration_state, config)
    graph.invoke(
        Command(
            update={
                "user_response": "approve",
                "approval_status": "approved",
                "waiting_for_user": False,
            }
        ),
        config,
    )

    assert "Supervisor" in langfuse_span_recorder
    assert "Planning" in langfuse_span_recorder
    assert "Research" in langfuse_span_recorder
    assert "Fitness" in langfuse_span_recorder
    assert "Verification" in langfuse_span_recorder
    assert "HITL" in langfuse_span_recorder
    assert "PERSIST_RESULTS" in langfuse_span_recorder

    supervisor_index = langfuse_span_recorder.index("Supervisor")
    planning_index = langfuse_span_recorder.index("Planning")
    research_index = langfuse_span_recorder.index("Research")
    persist_index = langfuse_span_recorder.index("PERSIST_RESULTS")
    assert supervisor_index < planning_index < research_index < persist_index


def test_langfuse_tavily_spans_under_active_trace(
    mock_tavily_client: TavilyMCPClient,
    langfuse_span_recorder: list[str],
) -> None:
    del mock_tavily_client
    token = set_trace_run_id("trace-run-tavily")
    try:
        search_tavily_data("hypertrophy training evidence")
        extract_tavily_data(["https://example.edu/fitness-training"])
    finally:
        reset_trace_run_id(token)

    assert TAVILY_SEARCH_TOOL in langfuse_span_recorder
    assert TAVILY_EXTRACT_TOOL in langfuse_span_recorder
    assert langfuse_span_recorder.index(TAVILY_SEARCH_TOOL) < langfuse_span_recorder.index(
        TAVILY_EXTRACT_TOOL
    )
