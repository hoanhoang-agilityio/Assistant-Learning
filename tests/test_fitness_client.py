"""Tests for api.deps._connect_with_retry -- bounded retry against a Fitness MCP
Server (own process) that may not have started yet."""

from __future__ import annotations

import pytest

from api.deps import _connect_with_retry
from core.adapters.mcp.fitness_client import FitnessMCPClient
from core.config.settings import get_settings

_SENTINEL = FitnessMCPClient(
    search_guidelines=lambda **kwargs: {},
    search_training_template=lambda fingerprint: {},
    store_training_template=lambda fingerprint, workout: {},
)


def test_connect_with_retry_returns_client_on_first_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.deps.create_fitness_mcp_client_sync", lambda settings: _SENTINEL)
    result = _connect_with_retry(get_settings(), max_attempts=3, backoff_seconds=0.0)
    assert result is _SENTINEL


def test_connect_with_retry_succeeds_after_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}

    def flaky(settings):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("not up yet")
        return _SENTINEL

    monkeypatch.setattr("api.deps.create_fitness_mcp_client_sync", flaky)
    result = _connect_with_retry(get_settings(), max_attempts=5, backoff_seconds=0.0)
    assert result is _SENTINEL
    assert attempts["count"] == 3


def test_connect_with_retry_returns_none_after_exhausting_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fails(settings):
        raise ConnectionError("never up")

    monkeypatch.setattr("api.deps.create_fitness_mcp_client_sync", always_fails)
    result = _connect_with_retry(get_settings(), max_attempts=3, backoff_seconds=0.0)
    assert result is None
