"""Deterministic default override for the Supervisor Router Judge.

Mirrors the shape of `tests/helpers/classification.py`'s judge stubs -- a simple,
inspectable stand-in for the real LLM call. Used as the autouse test default
(see conftest.py's `reset_supervisor_routing_judge`) so no test accidentally makes
a real LLM routing call; individual tests override it via
`configure_supervisor_routing_judge` when they need to script a specific decision.

Deliberately proposes the *simplest* next step at each point (e.g. always "finish"
after Fitness, never explicitly "verification") and trusts the Policy Engine
(`core.orchestration.routing.policy_engine`) to override into the hard-required path
(artifact_requires_verification, persist_requires_hitl_approval, etc.) -- this is
exactly the division of responsibility the hybrid design is built on, so the test
default should exercise it rather than hand-hold around it.
"""

from core.orchestration.agents.routing_context import RoutingContext
from core.orchestration.agents.supervisor_router_judge import SupervisorRoutingJudgement

_ENTRY_BY_INTENT = {
    "build_plan": "planning",
    "edit_plan": "fitness",
    "verify_plan": "fitness",
    "verify_macros": "fitness",
    "calculate_calories": "fitness",
    "research_question": "research",
    "fitness_question": "fitness",
}


def _entry_for(ctx: RoutingContext) -> str:
    for intent, entry in _ENTRY_BY_INTENT.items():
        if f"intent={intent}" in ctx.request_summary:
            return entry
    return "planning"


def default_supervisor_routing_judge(ctx: RoutingContext) -> SupervisorRoutingJudgement:
    last = ctx.last_agent_result

    if last is None:
        return SupervisorRoutingJudgement(
            next_agent=_entry_for(ctx), reason="entry", confidence=1.0
        )

    if last.status == "failed":
        return SupervisorRoutingJudgement(next_agent="finish", reason="failed", confidence=1.0)

    if last.status == "blocked":
        if "research_findings" in last.missing_information:
            return SupervisorRoutingJudgement(
                next_agent="research", reason="needs research", confidence=1.0
            )
        return SupervisorRoutingJudgement(next_agent="user", reason="needs profile", confidence=1.0)

    next_by_capability = {
        "planning": "fitness",
        "research": "fitness",
        "fitness": "finish",
        "verification": "hitl",
        "hitl": "persist",
        "persist": "finish",
    }
    if last.capability == "user":
        return SupervisorRoutingJudgement(
            next_agent=_entry_for(ctx), reason="profile complete", confidence=1.0
        )
    next_agent = next_by_capability.get(last.capability, "finish")
    return SupervisorRoutingJudgement(next_agent=next_agent, reason="happy path", confidence=1.0)
