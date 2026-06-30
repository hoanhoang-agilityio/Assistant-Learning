from unittest.mock import MagicMock, patch

import pytest

from core.agents.state import OrchestrationState
from core.config.settings import Settings
from core.observability.tracing import (
    PARTIAL_RERUN_DECISIONS,
    SUBGRAPH_SPAN_NAMES,
    resolve_subgraph_span_name,
    wrap_traced_subgraph_node,
)


def test_resolve_subgraph_span_names() -> None:
    assert resolve_subgraph_span_name("planning", None) == "Planning"
    assert resolve_subgraph_span_name("research", None) == "Research"
    assert resolve_subgraph_span_name("persist", None) == "PERSIST_RESULTS"
    assert resolve_subgraph_span_name("planning", "REPLAN") == "partial_rerun_REPLAN"
    assert resolve_subgraph_span_name("research", "RERESEARCH") == "partial_rerun_RERESEARCH"
    assert resolve_subgraph_span_name("fitness", "FIX_REASONING") == "partial_rerun_FIX_REASONING"


def test_partial_rerun_decisions_cover_spec() -> None:
    assert PARTIAL_RERUN_DECISIONS == frozenset({"FIX_REASONING", "REPLAN", "RERESEARCH"})


def test_subgraph_span_names_match_hierarchy() -> None:
    assert set(SUBGRAPH_SPAN_NAMES.values()) == {
        "Planning",
        "Research",
        "Fitness",
        "Verification",
        "HITL",
        "PERSIST_RESULTS",
    }


@patch("core.observability.langfuse.subgraph_span_context")
def test_wrap_traced_subgraph_node_opens_span(
    mock_span_context: MagicMock,
    orchestration_state: OrchestrationState,
) -> None:
    mock_span = MagicMock()
    mock_span_context.return_value.__enter__.return_value = mock_span

    def invoke_fn(state: OrchestrationState) -> dict:
        return {"current_node": "planning", "query": state["query"]}

    traced = wrap_traced_subgraph_node("planning", invoke_fn)
    result = traced(orchestration_state)

    mock_span_context.assert_called_once()
    call_args = mock_span_context.call_args
    assert call_args.args[1] == "Planning"
    assert call_args.kwargs["tier"] == "XHIGH"
    mock_span.update.assert_called_once_with(output=result)


@patch("core.observability.langfuse.get_langfuse_client")
def test_tavily_tool_span_uses_run_trace(
    mock_get_client: MagicMock,
    langfuse_settings: Settings,
) -> None:
    from core.observability.langfuse import tavily_tool_span_context

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.create_trace_id.return_value = "trace-abc"

    with tavily_tool_span_context(
        "run-1",
        "tavily-search",
        input_data={"query": "hypertrophy"},
        settings=langfuse_settings,
    ):
        pass

    mock_client.start_as_current_span.assert_called_once()
    call_kwargs = mock_client.start_as_current_span.call_args.kwargs
    assert call_kwargs["name"] == "tavily-search"
    assert call_kwargs["trace_context"] == {"trace_id": "trace-abc"}


@pytest.fixture
def langfuse_settings() -> Settings:
    return Settings(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://localhost:3000",
    )


def test_langfuse_base_url_prefers_base_url_env() -> None:
    settings = Settings.model_validate(
        {
            "LANGFUSE_BASE_URL": "http://localhost:3000",
            "LANGFUSE_HOST": "https://cloud.langfuse.com",
        }
    )
    assert settings.langfuse_base_url == "http://localhost:3000"


@patch("core.observability.langfuse.httpx.get")
def test_get_langfuse_client_disables_on_unauthorized(mock_get: MagicMock) -> None:
    from core.observability.langfuse import get_langfuse_client, reset_langfuse_client

    reset_langfuse_client()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.return_value = mock_response
    settings = Settings(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://localhost:3000",
    )
    assert get_langfuse_client(settings) is None
    assert get_langfuse_client(settings) is None
    mock_get.assert_called_once()
    reset_langfuse_client()
