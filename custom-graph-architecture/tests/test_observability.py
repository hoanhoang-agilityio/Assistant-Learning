"""Tests for Langfuse wiring and the run config.

The rule these enforce: tracing never breaks a request. Every failure path — disabled,
unconfigured, bad credentials, an exception inside the SDK — must leave the app serving with
tracing off, not raise.
"""

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import structlog

from src.configs.config import settings
from src.observability import build_run_config, langfuse
from src.observability.langfuse import (
    get_langfuse_callbacks,
    langfuse_init,
    langfuse_shutdown,
)
from src.observability.tracing import TURN_TRACE_NAME
from src.runtime import facade
from src.runtime.facade import langgraph_runtime


@pytest.fixture(autouse=True)
def reset_handler():
    """Clear module-level state so each test starts from an uninitialised process."""
    langfuse._callback_handler = None
    langfuse._client = None
    yield
    langfuse._callback_handler = None
    langfuse._client = None


def test_no_callbacks_before_init() -> None:
    """A graph run before startup traces nothing rather than failing."""
    assert get_langfuse_callbacks() == []


def test_init_is_a_noop_when_tracing_is_disabled() -> None:
    """LANGFUSE_TRACING_ENABLED=false must not touch the network."""
    with patch.object(settings, "LANGFUSE_TRACING_ENABLED", False):
        with patch.object(langfuse, "Langfuse") as client:
            langfuse_init()

    client.assert_not_called()
    assert get_langfuse_callbacks() == []


def test_init_skips_when_keys_are_missing() -> None:
    """A dev machine with no keys gets tracing off, not a crash."""
    with (
        patch.object(settings, "LANGFUSE_TRACING_ENABLED", True),
        patch.object(settings, "LANGFUSE_PUBLIC_KEY", ""),
        patch.object(settings, "LANGFUSE_SECRET_KEY", ""),
        patch.object(langfuse, "Langfuse") as client,
    ):
        langfuse_init()

    client.assert_not_called()
    assert get_langfuse_callbacks() == []


def test_failed_auth_check_leaves_tracing_off() -> None:
    """Wrong credentials must not attach a handler that silently drops spans."""
    with (
        patch.object(settings, "LANGFUSE_TRACING_ENABLED", True),
        patch.object(settings, "LANGFUSE_PUBLIC_KEY", "pk"),
        patch.object(settings, "LANGFUSE_SECRET_KEY", "sk"),
        patch.object(langfuse, "Langfuse") as client,
    ):
        client.return_value.auth_check.return_value = False
        langfuse_init()

    assert get_langfuse_callbacks() == []


def test_sdk_exception_is_swallowed() -> None:
    """An unreachable Langfuse host cannot take the application down."""
    with (
        patch.object(settings, "LANGFUSE_TRACING_ENABLED", True),
        patch.object(settings, "LANGFUSE_PUBLIC_KEY", "pk"),
        patch.object(settings, "LANGFUSE_SECRET_KEY", "sk"),
        patch.object(langfuse, "Langfuse", side_effect=ConnectionError("host down")),
    ):
        langfuse_init()

    assert get_langfuse_callbacks() == []


def test_successful_init_attaches_exactly_one_handler() -> None:
    """One handler per process — a second would duplicate every span."""
    with (
        patch.object(settings, "LANGFUSE_TRACING_ENABLED", True),
        patch.object(settings, "LANGFUSE_PUBLIC_KEY", "pk"),
        patch.object(settings, "LANGFUSE_SECRET_KEY", "sk"),
        patch.object(langfuse, "Langfuse") as client,
        patch.object(langfuse, "CallbackHandler", return_value=MagicMock()),
    ):
        client.return_value.auth_check.return_value = True
        langfuse_init()
        langfuse_init()

    assert len(get_langfuse_callbacks()) == 1


def test_shutdown_flushes_the_configured_client() -> None:
    """Flushing a freshly constructed client would hit a credential-less, disabled one."""
    with (
        patch.object(settings, "LANGFUSE_TRACING_ENABLED", True),
        patch.object(settings, "LANGFUSE_PUBLIC_KEY", "pk"),
        patch.object(settings, "LANGFUSE_SECRET_KEY", "sk"),
        patch.object(langfuse, "Langfuse") as client,
        patch.object(langfuse, "CallbackHandler", return_value=MagicMock()),
    ):
        client.return_value.auth_check.return_value = True
        langfuse_init()
        configured = client.return_value
        client.reset_mock()

        langfuse_shutdown()

    configured.flush.assert_called_once()
    client.assert_not_called()


def test_shutdown_is_safe_when_never_initialised() -> None:
    """Shutting down an app whose tracing never started must not raise."""
    langfuse_shutdown()


def test_run_config_promotes_session_and_user_for_langfuse() -> None:
    """Only the langfuse_-prefixed keys become the trace's own session/user fields.

    Without them the trace is unfilterable by user or conversation, which is exactly what
    spec §10 asks tracing to provide.
    """
    metadata = build_run_config("session-1", "user-1")["metadata"]

    assert metadata["langfuse_session_id"] == "session-1"
    assert metadata["langfuse_user_id"] == "user-1"


def test_run_config_carries_the_checkpoint_thread() -> None:
    """thread_id is both the checkpoint lineage and the Langfuse session."""
    config = build_run_config(session_id="session-1", user_id="user-1")

    assert config["configurable"]["thread_id"] == "session-1"


def test_run_config_metadata_carries_the_spec_identifiers() -> None:
    """Spec §10 requires a trace to be findable by run_id and user_id."""
    config = build_run_config(session_id="session-1", user_id="user-1")

    assert config["metadata"]["user_id"] == "user-1"
    assert config["metadata"]["session_id"] == "session-1"
    assert config["metadata"]["environment"] == settings.ENVIRONMENT.value
    assert config["metadata"]["run_id"]


def test_run_id_is_generated_per_turn_unless_supplied() -> None:
    """Two turns in one session are distinguishable; an explicit id is respected."""
    first = build_run_config("session-1", "user-1")
    second = build_run_config("session-1", "user-1")

    assert first["metadata"]["run_id"] != second["metadata"]["run_id"]
    assert build_run_config("s", "u", run_id="fixed")["metadata"]["run_id"] == "fixed"


def test_run_config_has_no_callbacks_when_tracing_is_off() -> None:
    """The config is still valid to invoke with; it just carries no handler."""
    config = build_run_config(session_id="session-1", user_id="user-1")

    assert config["callbacks"] == []


def test_the_trace_is_named_and_tagged_with_its_environment() -> None:
    """Unnamed, every trace is titled after the compiled graph and none is findable."""
    config = build_run_config(session_id="session-1", user_id="user-1")

    assert config["run_name"] == TURN_TRACE_NAME
    assert config["tags"] == [settings.ENVIRONMENT.value]


# --- The turn's own line: latency and final result ----------------------------------------


@dataclass
class _FakeState:
    """What ``aget_state`` returns, reduced to what the facade reads off it."""

    values: dict[str, Any]
    next: tuple = ()
    tasks: tuple = ()


@dataclass
class _FakeGraph:
    """A graph that has already run, parked at the state a turn settled on."""

    values: dict[str, Any] = field(default_factory=dict)

    async def aget_state(self, _config) -> _FakeState:
        return _FakeState(values=self.values)


@pytest.fixture
def turn_log(monkeypatch: pytest.MonkeyPatch) -> dict:
    """The keyword arguments of the ``turn_completed`` line, as the log store would see them.

    The module logger is replaced rather than structlog reconfigured: the logger is cached
    on first use, so a swapped processor chain never reaches the one the facade holds.
    """
    captured: dict = {}
    recorder = MagicMock()
    recorder.info.side_effect = lambda event, **fields: captured.update(
        {"event": event, **fields}
    )
    monkeypatch.setattr(facade, "logger", recorder)
    return captured


async def _finish(values: dict[str, Any]) -> None:
    """Run the facade's turn-completion path over a state a run has settled on."""
    config = build_run_config("session-1", "user-1")
    await langgraph_runtime._finish_turn(
        _FakeGraph(values=values), config, before=0, started=perf_counter()
    )


async def test_a_finished_turn_reports_its_latency(turn_log) -> None:
    """Spec §10 asks for latency, which is one line per turn."""
    await _finish({"messages": []})

    assert turn_log["event"] == "turn_completed"
    assert turn_log["duration_ms"] >= 0
    assert turn_log["paused"] is False


async def test_a_finished_turn_reports_the_counters_it_ended_on(turn_log) -> None:
    """Retry counts on the turn line make a run comparable without reading its spans."""
    await _finish(
        {
            "messages": [],
            "next": "coach_agent",
            "coach_retry_count": 2,
            "approval_decision": "approve",
        }
    )

    assert turn_log["next"] == "coach_agent"
    assert turn_log["coach_retry_count"] == 2
    assert turn_log["approval_decision"] == "approve"


async def test_a_turn_that_never_reached_a_branch_reports_no_counters_for_it(
    turn_log,
) -> None:
    """A QA turn logging ``approval_decision=None`` invites a search that finds nothing."""
    await _finish({"messages": [], "next": "qa_agent", "faithfulness_score": 0.94})

    assert turn_log["faithfulness_score"] == 0.94
    assert "approval_decision" not in turn_log


def test_the_turn_binds_its_run_id_to_every_line_it_produces() -> None:
    """run_id is per turn, not per request: it is what stitches node lines to the trace."""
    config, _started = langgraph_runtime._start_turn("session-1", "user-1")

    assert (
        structlog.contextvars.get_contextvars()["run_id"]
        == config["metadata"]["run_id"]
    )
