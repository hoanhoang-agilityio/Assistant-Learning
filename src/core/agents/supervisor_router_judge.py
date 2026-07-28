"""LLM judge for Supervisor semantic routing.

This judge proposes the next capability only -- it must never enforce a business
rule itself. Every proposal is validated/overridden by the deterministic Policy
Engine (`core.capabilities.policy_engine`) before it is used to route the graph.
"""

from collections.abc import Callable
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.agents.routing_context import RoutingContext
from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.payload import compact_json
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION

SUPERVISOR_ROUTER_PROMPT_VERSION = "v1"

RoutingDecision = Literal[
    "user",
    "planning",
    "research",
    "fitness",
    "verification",
    "hitl",
    "persist",
    "finish",
]


class SupervisorRoutingJudgement(BaseModel):
    """LLM proposal for the next capability to run.

    Purely a proposal -- the Policy Engine may override `next_agent` if it violates
    a hard business rule (profile-gate, verification-before-persist, HITL-before-
    persist, hop limits). This model never carries enforcement logic of its own.
    """

    next_agent: RoutingDecision
    reason: str = Field(description="One short sentence explaining the proposed route.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this proposal, 0-1.")


SupervisorRoutingJudge = Callable[[RoutingContext], SupervisorRoutingJudgement]

_JUDGE_OVERRIDE: SupervisorRoutingJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """You are the Supervisor for a fitness planning assistant orchestrating several
capabilities (agents). After every capability finishes, you decide which capability
should run next based on its reported status.

You will receive a compact routing context with:
- current_agent: the capability that just ran (or null on the very first hop)
- last_agent_result: that capability's reported status
  - "completed": it finished its own work successfully
  - "blocked": it cannot proceed without something listed in missing_information
  - "failed": it hit an unrecoverable error
- agent_trail: the last few capabilities visited, in order (oldest first) -- use
  this to decide where to *return* to (e.g. if fitness was blocked on research and
  research just completed, route back to fitness, not straight to finish)
- available_agents: the only valid values for next_agent, each with a description
  of what it does
- guardrail_state: informational only (hop_count, profile status, revision count)
  -- you do not need to enforce these yourself, a deterministic checker does that
  after your decision
- request_summary: the original user request and classified intent

Your job is ONLY semantic routing -- deciding which valid capability makes sense
next given what just happened. You must NOT try to enforce business rules
yourself (e.g. "profile must exist before planning") -- a separate deterministic
system does that and will override you if needed, so just make the best semantic
call from the agent statuses you're given.

Pick "finish" when the run's goal has been satisfied and no further capability is
needed (e.g. a read-only question was fully answered, or an artifact has completed
its full lifecycle).

next_agent must be exactly one of the values listed in available_agents (or
"finish")."""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_supervisor_routing_judge(judge: SupervisorRoutingJudge | None) -> None:
    global _JUDGE_OVERRIDE
    _JUDGE_OVERRIDE = judge


def judge_next_route(ctx: RoutingContext) -> SupervisorRoutingJudgement:
    if _JUDGE_OVERRIDE is not None:
        return _JUDGE_OVERRIDE(ctx)
    token = set_llm_metrics_node("supervisor_router")
    try:
        return invoke_standard_structured_output(
            SupervisorRoutingJudgement,
            [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=compact_json(ctx.model_dump(mode="json"))),
            ],
            prompt_cache_key="supervisor_router",
        )
    finally:
        reset_llm_metrics_node(token)
