"""Unit tests for Langfuse Runs → Traces → Threads hierarchy mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.agents.state import OrchestrationState
from core.config.settings import Settings
from core.observability.hierarchy import (
    LANGFUSE_SESSION_METADATA_KEY,
    describe_hierarchy_mapping,
    hierarchy_propagation_metadata,
    langfuse_thread_context,
    map_run_to_trace_seed,
    map_thread_to_session_id,
    resolve_hierarchy_ids,
)
from core.observability.langfuse import (
    build_graph_invoke_config,
    fetch_langfuse_thread,
    resolve_run_hierarchy,
    subgraph_span_context,
)


def test_map_thread_to_session_id_is_identity() -> None:
    assert map_thread_to_session_id("thread-abc") == "thread-abc"


def test_map_run_to_trace_seed_is_identity() -> None:
    assert map_run_to_trace_seed("run-xyz") == "run-xyz"


def test_resolve_hierarchy_ids_bundle() -> None:
    ids = resolve_hierarchy_ids(run_id="run-1", thread_id="thread-1", trace_id="trace-1")
    assert ids.run_id == "run-1"
    assert ids.thread_id == "thread-1"
    assert ids.trace_id == "trace-1"
    assert ids.session_id == "thread-1"
    assert ids.langfuse_session_metadata[LANGFUSE_SESSION_METADATA_KEY] == "thread-1"
    assert ids.langfuse_session_metadata["run_id"] == "run-1"


def test_hierarchy_propagation_metadata_is_string_valued() -> None:
    ids = resolve_hierarchy_ids(run_id="run-1", thread_id="thread-1")
    metadata = hierarchy_propagation_metadata(ids)
    assert all(isinstance(value, str) for value in metadata.values())
    assert metadata[LANGFUSE_SESSION_METADATA_KEY] == "thread-1"


def test_describe_hierarchy_mapping_documents_session_as_thread() -> None:
    mapping = describe_hierarchy_mapping()
    assert mapping["thread"]["langfuse_concept"] == "session"
    assert mapping["run"]["langfuse_concept"] == "trace"
    assert "Session(thread_id)" in mapping["hierarchy"]


def test_build_graph_invoke_config_binds_session_and_trace(
    orchestration_state: OrchestrationState,
) -> None:
    settings = Settings(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://localhost:3000",
    )
    with (
        patch("core.observability.langfuse.build_langfuse_callbacks", return_value=["handler"]),
        patch(
            "core.observability.langfuse.create_trace_id_for_run",
            return_value="trace-from-run",
        ),
    ):
        config = build_graph_invoke_config(orchestration_state, settings=settings)
    assert config["configurable"]["thread_id"] == orchestration_state["thread_id"]
    assert config["metadata"][LANGFUSE_SESSION_METADATA_KEY] == orchestration_state["thread_id"]
    assert config["metadata"]["run_id"] == orchestration_state["run_id"]
    assert config["metadata"]["langfuse_trace_id"] == "trace-from-run"
    assert config["callbacks"] == ["handler"]


def test_resolve_run_hierarchy_uses_deterministic_trace(
    orchestration_state: OrchestrationState,
) -> None:
    with patch(
        "core.observability.langfuse.create_trace_id_for_run",
        return_value="deterministic-trace",
    ):
        ids = resolve_run_hierarchy(orchestration_state, settings=Settings())
    assert ids.session_id == orchestration_state["thread_id"]
    assert ids.trace_id == "deterministic-trace"


def test_fetch_langfuse_thread_calls_sessions_api() -> None:
    settings = Settings(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://localhost:3000",
        langfuse_tracing_enabled=True,
    )
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"id": "thread-42", "traces": []}
    with (
        patch("core.observability.langfuse.is_langfuse_enabled", return_value=True),
        patch("core.observability.langfuse.httpx.get", return_value=response) as mock_get,
    ):
        payload = fetch_langfuse_thread("thread-42", settings=settings)
    assert payload == {"id": "thread-42", "traces": []}
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "http://localhost:3000/api/public/sessions/thread-42"


def test_fetch_langfuse_thread_returns_none_on_404() -> None:
    settings = Settings(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://localhost:3000",
        langfuse_tracing_enabled=True,
    )
    response = MagicMock()
    response.status_code = 404
    with (
        patch("core.observability.langfuse.is_langfuse_enabled", return_value=True),
        patch("core.observability.langfuse.httpx.get", return_value=response),
    ):
        assert fetch_langfuse_thread("missing", settings=settings) is None


def test_fetch_langfuse_thread_returns_none_when_disabled() -> None:
    assert fetch_langfuse_thread("thread-1", settings=Settings()) is None


def test_subgraph_span_binds_thread_session(
    orchestration_state: OrchestrationState,
) -> None:
    mock_client = MagicMock()
    span_cm = MagicMock()
    span_cm.__enter__.return_value = MagicMock()
    span_cm.__exit__.return_value = None
    mock_client.start_as_current_span.return_value = span_cm
    mock_client.create_trace_id.return_value = "trace-1"
    with (
        patch("core.observability.langfuse.get_langfuse_client", return_value=mock_client),
        patch("core.observability.langfuse.langfuse_thread_context") as mock_thread_ctx,
    ):
        mock_thread_ctx.return_value.__enter__.return_value = resolve_hierarchy_ids(
            run_id=orchestration_state["run_id"],
            thread_id=orchestration_state["thread_id"],
            trace_id="trace-1",
        )
        mock_thread_ctx.return_value.__exit__.return_value = None
        with subgraph_span_context(orchestration_state, "Research", subgraph="research"):
            pass
    mock_thread_ctx.assert_called_once_with(
        orchestration_state["thread_id"],
        run_id=orchestration_state["run_id"],
    )
    mock_client.start_as_current_span.assert_called_once()
    call_kwargs = mock_client.start_as_current_span.call_args.kwargs
    assert call_kwargs["metadata"]["thread_id"] == orchestration_state["thread_id"]
    assert (
        call_kwargs["metadata"][LANGFUSE_SESSION_METADATA_KEY] == orchestration_state["thread_id"]
    )


def test_langfuse_thread_context_calls_propagate_attributes() -> None:
    with patch("core.observability.hierarchy.propagate_attributes") as mock_propagate:
        mock_propagate.return_value.__enter__.return_value = None
        mock_propagate.return_value.__exit__.return_value = None
        with langfuse_thread_context("thread-9", run_id="run-9") as ids:
            assert ids.session_id == "thread-9"
            assert ids.run_id == "run-9"
    mock_propagate.assert_called_once()
    kwargs = mock_propagate.call_args.kwargs
    assert kwargs["session_id"] == "thread-9"
    assert kwargs["metadata"][LANGFUSE_SESSION_METADATA_KEY] == "thread-9"
