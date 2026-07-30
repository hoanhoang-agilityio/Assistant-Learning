"""Phase 1: wires the Supervisor Router Judge + Policy Engine into the graph,
behind `settings.supervisor_router_enabled`.

Builds a compact `RoutingContext` from orchestration state, gets a proposal from
the Router Judge, and enforces deterministic business rules via the Policy Engine
before returning the final routing decision to store in state. This module owns
no business rules itself -- see `core.orchestration.routing.policy_engine` for those.
"""

from __future__ import annotations

from typing import Any

from core.observability.langfuse import supervisor_routing_span_context
from core.orchestration.agents.execution_context import CapabilityResult
from core.orchestration.agents.routing_context import (
    AgentDescriptor,
    AgentResultSummary,
    GuardrailState,
    RoutingContext,
    append_agent_trail,
    summarize_agent_result,
)
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.agents.supervisor_log import append_supervisor_decision
from core.orchestration.agents.supervisor_router_judge import (
    SUPERVISOR_ROUTER_PROMPT_VERSION,
    judge_next_route,
)
from core.orchestration.routing.policy_engine import enforce_routing_invariants
from core.orchestration.routing.registry import CAPABILITY_REGISTRY


def _available_agents() -> list[AgentDescriptor]:
    return [
        AgentDescriptor(name=defn.name, description=defn.description)
        for defn in CAPABILITY_REGISTRY.values()
    ]


def _last_agent_result(state: OrchestrationState) -> AgentResultSummary | None:
    raw = state.get("last_capability_result")
    if not raw:
        return None
    return summarize_agent_result(CapabilityResult.model_validate(raw))


def build_routing_context(state: OrchestrationState, *, max_hops: int) -> RoutingContext:
    last = state.get("last_capability_result") or {}
    return RoutingContext(
        current_agent=last.get("capability"),
        last_agent_result=_last_agent_result(state),
        agent_trail=list(state.get("agent_trail") or []),
        available_agents=_available_agents(),
        guardrail_state=GuardrailState(
            hop_count=int(state.get("hop_count") or 0),
            max_hops=max_hops,
            profile_complete=bool(state.get("profile_complete")),
            profile_valid=bool(state.get("profile_valid")),
            revision_count=int(state.get("revision_count") or 0),
        ),
        request_summary=f"{state.get('query', '')} (intent={state.get('intent')})",
    )


def run_supervisor_routing_decision(
    state: OrchestrationState, *, max_hops: int, max_verification_retry_attempts: int = 1
) -> dict[str, Any]:
    """Propose + enforce the next routing hop.

    Returns a state update dict with `next_agent`, `hop_count`, `agent_trail`, and
    (if finishing) `run_complete`/`final_response`. Called from `supervisor_node`
    on every hop once `settings.supervisor_router_enabled` is on.
    """
    ctx = build_routing_context(state, max_hops=max_hops)
    with supervisor_routing_span_context(
        state, routing_context=ctx.model_dump(mode="json")
    ) as span:
        proposal = judge_next_route(ctx)
        decision = enforce_routing_invariants(
            state,
            proposal,
            max_hops=max_hops,
            max_verification_retry_attempts=max_verification_retry_attempts,
        )
        if span is not None:
            span.update(
                output={"next_agent": decision.next_agent, "overridden": decision.overridden}
            )

    append_supervisor_decision(
        state["workspace_path"],
        {
            "run_id": state.get("run_id"),
            "hop_count": ctx.guardrail_state.hop_count,
            "current_agent": ctx.current_agent,
            "proposed_next_agent": proposal.next_agent,
            "final_next_agent": decision.next_agent,
            "reason": proposal.reason,
            "confidence": proposal.confidence,
            "policy_overridden": decision.overridden,
            "policy_reason": decision.override_reason,
            "prompt_version": SUPERVISOR_ROUTER_PROMPT_VERSION,
        },
    )

    updates: dict[str, Any] = {
        "next_agent": decision.next_agent,
        "hop_count": ctx.guardrail_state.hop_count + 1,
        "agent_trail": append_agent_trail(list(state.get("agent_trail") or []), ctx.current_agent),
        # Surfaced by the API/UI for run-progress display (src/api/schemas.py,
        # serializers.py) -- previously set by the dispatcher's request-forwarding;
        # now just reflects the Supervisor's own resolved decision.
        "active_capability": None if decision.next_agent == "finish" else decision.next_agent,
    }
    if decision.override_reason == "verification_failed_auto_retry":
        updates["verification_retry_count"] = int(state.get("verification_retry_count") or 0) + 1
    if decision.next_agent == "finish":
        updates["run_complete"] = True
        last_result = state.get("last_capability_result") or {}
        if last_result.get("summary"):
            updates["final_response"] = last_result["summary"]
    return updates
