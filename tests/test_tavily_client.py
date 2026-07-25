"""Tests for Tavily MCP client deadlines (PR2).

No existing test file exercises tavily_client.py's real invocation path --
tests/conftest.py's mock_tavily_client fixture builds a TavilyMCPClient via
core.mcp.mock_tavily, which bypasses _invoke_tool/_run_async/
create_tavily_mcp_client entirely. This file covers the real path directly.
"""

import asyncio

import pytest

from core.config.settings import Settings
from core.mcp.tavily_client import _invoke_tool, create_tavily_mcp_client


class _SlowTool:
    """Stand-in for a BaseTool whose MCP call never returns in time."""

    name = "tavily_search"

    async def ainvoke(self, payload: dict) -> dict:
        del payload
        await asyncio.sleep(1.0)
        return {"results": []}


class _FastTool:
    """Stand-in for a BaseTool that responds well within the deadline."""

    name = "tavily_search"

    async def ainvoke(self, payload: dict) -> dict:
        del payload
        return {"results": [{"content": "ok"}]}


class _SlowMCPClient:
    """Stand-in for MultiServerMCPClient whose handshake never returns in time."""

    def __init__(self, connections: dict) -> None:
        del connections

    async def get_tools(self) -> list:
        await asyncio.sleep(1.0)
        return []


def test_invoke_tool_times_out_when_tool_call_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression (PR2): a Tavily tool call that never returns must raise within
    the configured deadline instead of blocking the research subgraph forever."""
    settings = Settings(tavily_tool_timeout_seconds=0.05)
    monkeypatch.setattr("core.mcp.tavily_client.get_settings", lambda: settings)

    with pytest.raises(TimeoutError):
        _invoke_tool(_SlowTool(), {"query": "test"})


def test_invoke_tool_returns_normally_within_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool call that finishes well inside the deadline is unaffected."""
    settings = Settings(tavily_tool_timeout_seconds=5.0)
    monkeypatch.setattr("core.mcp.tavily_client.get_settings", lambda: settings)

    result = _invoke_tool(_FastTool(), {"query": "test"})

    assert result == {"results": [{"content": "ok"}]}


def test_create_tavily_mcp_client_times_out_on_slow_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (PR2): a hanging MCP tool-listing handshake must raise within
    the configured deadline instead of blocking client creation forever."""
    monkeypatch.setattr("core.mcp.tavily_client.MultiServerMCPClient", _SlowMCPClient)
    settings = Settings(tavily_api_key="test-key", tavily_tool_timeout_seconds=0.05)

    with pytest.raises(TimeoutError):
        asyncio.run(create_tavily_mcp_client(settings=settings))
