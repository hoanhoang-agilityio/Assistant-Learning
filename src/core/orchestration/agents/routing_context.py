"""Compact per-hop input to the Supervisor Router Judge.

Deliberately excludes full orchestration state and full artifact payloads to keep
token usage low -- see the hybrid Supervisor routing design doc for the rationale.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.orchestration.agents.execution_context import (
    CapabilityName,
    CapabilityResult,
    CapabilityStatus,
)


class AgentDescriptor(BaseModel):
    """Identity/description of one routable capability, for the Router Judge's prompt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: CapabilityName
    description: str


class AgentResultSummary(BaseModel):
    """Compact projection of `CapabilityResult` -- omits `artifacts`/`metadata` so the
    Router Judge never pays token cost for full domain payloads it doesn't route on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: CapabilityName
    status: CapabilityStatus
    blocking_reason: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    summary: str = ""


def summarize_agent_result(result: CapabilityResult) -> AgentResultSummary:
    """Project a full `CapabilityResult` down to what the Router Judge should see."""
    return AgentResultSummary(
        capability=result.capability,
        status=result.status,
        blocking_reason=result.blocking_reason,
        missing_information=result.missing_information,
        summary=result.summary,
    )


class GuardrailState(BaseModel):
    """Deterministic guardrail signals surfaced to the Router Judge as context only --
    enforcement always happens in the Policy Engine, never left to the LLM's judgment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hop_count: int
    max_hops: int
    profile_complete: bool
    profile_valid: bool
    revision_count: int


class RoutingContext(BaseModel):
    """Compact routing input built fresh on every Supervisor hop."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    current_agent: str | None
    last_agent_result: AgentResultSummary | None
    agent_trail: list[str] = Field(default_factory=list)
    available_agents: list[AgentDescriptor]
    guardrail_state: GuardrailState
    request_summary: str


_MAX_AGENT_TRAIL = 5


def append_agent_trail(trail: list[str], capability: str | None) -> list[str]:
    """Append a capability to the trail, keeping only the most recent entries."""
    if capability is None:
        return list(trail)
    return [*trail, capability][-_MAX_AGENT_TRAIL:]
