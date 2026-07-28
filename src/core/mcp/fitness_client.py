"""LangChain MCP Adapters client for the Fitness MCP Server (own process).

Mirrors core.mcp.tavily_client's shape, but the Fitness MCP Server is owned by this
repo (not a pre-built external server) and is constructed exactly once at FastAPI
startup and cached for the process lifetime -- see
api/deps.py::configure_fitness_client_from_settings. get_fitness_client() returns None
rather than rebuilding when unconfigured/unreachable, so every call site has exactly
one failure shape to handle (see core.subgraphs.fitness.template_registry,
core.subgraphs.research.utils).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from core.config.settings import Settings, get_settings
from core.mcp._transport import invoke_tool, resolve_tool_name

SEARCH_GUIDELINES_TOOL = "search_guidelines"
SEARCH_TRAINING_TEMPLATE_TOOL = "search_training_template"
STORE_TRAINING_TEMPLATE_TOOL = "store_training_template"


@dataclass(frozen=True)
class FitnessMCPClient:
    """Thin wrapper around the Fitness MCP Server's tools."""

    search_guidelines: Callable[..., dict[str, Any]]
    search_training_template: Callable[[str], dict[str, Any]]
    store_training_template: Callable[[str, dict[str, Any]], dict[str, Any]]


def build_fitness_connections(settings: Settings) -> dict[str, dict[str, Any]]:
    return {
        "fitness": {
            "transport": "streamable_http",
            "url": f"http://{settings.fitness_mcp_host}:{settings.fitness_mcp_port}/mcp",
        }
    }


async def create_fitness_mcp_client(settings: Settings | None = None) -> FitnessMCPClient:
    """Connect to the Fitness MCP Server and load its tools via langchain-mcp-adapters."""
    resolved_settings = settings or get_settings()
    connections = build_fitness_connections(resolved_settings)
    client = MultiServerMCPClient(connections=connections)
    timeout = resolved_settings.fitness_mcp_tool_timeout_seconds
    tools = await asyncio.wait_for(client.get_tools(), timeout=timeout)
    tools_by_name = {tool.name: tool for tool in tools}

    required = (SEARCH_GUIDELINES_TOOL, SEARCH_TRAINING_TEMPLATE_TOOL, STORE_TRAINING_TEMPLATE_TOOL)
    missing = [name for name in required if resolve_tool_name(tools_by_name, (name,)) is None]
    if missing:
        available = ", ".join(sorted(tools_by_name))
        raise RuntimeError(f"Missing Fitness MCP tools {missing}. Available: {available}")

    search_guidelines_tool = tools_by_name[SEARCH_GUIDELINES_TOOL]
    search_template_tool = tools_by_name[SEARCH_TRAINING_TEMPLATE_TOOL]
    store_template_tool = tools_by_name[STORE_TRAINING_TEMPLATE_TOOL]
    return FitnessMCPClient(
        search_guidelines=lambda **kwargs: invoke_tool(
            search_guidelines_tool, kwargs, timeout=timeout
        ),
        search_training_template=lambda fingerprint: invoke_tool(
            search_template_tool, {"fingerprint": fingerprint}, timeout=timeout
        ),
        store_training_template=lambda fingerprint, workout: invoke_tool(
            store_template_tool,
            {"fingerprint": fingerprint, "workout": workout},
            timeout=timeout,
        ),
    )


def create_fitness_mcp_client_sync(settings: Settings | None = None) -> FitnessMCPClient:
    """Synchronous helper for non-async call sites."""
    return asyncio.run(create_fitness_mcp_client(settings=settings))


_client: FitnessMCPClient | None = None


def configure_fitness_client(client: FitnessMCPClient | None) -> None:
    """Inject or reset the Fitness MCP client (used at startup and in tests)."""
    global _client
    _client = client


def get_fitness_client() -> FitnessMCPClient | None:
    """Return the configured Fitness MCP client, or None if unconfigured/unreachable.

    Unlike get_tavily_client(), this never lazily rebuilds -- the client is
    constructed exactly once at FastAPI startup (api/deps.py) and cached for the
    process lifetime. Every call site treats None the same as a failed call: degrade
    gracefully (see core.subgraphs.fitness.template_registry, core.subgraphs.research.utils).
    """
    return _client
