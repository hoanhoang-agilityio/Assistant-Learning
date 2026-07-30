"""Per-node LLM payload and token budgets derived from representative fixture measurements."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from core.adapters.llm.metrics import estimate_payload_tokens
from core.adapters.llm.payload import compact_json


@dataclass(frozen=True)
class LlmNodeBudget:
    """Token budget for a single LLM node."""

    node: str
    max_input_tokens: int
    exception_note: str | None = None
    # Per-node override of the node's tier-level reasoning_effort default
    # (settings.openai_standard_reasoning_effort / openai_xhigh_reasoning_effort).
    # None means "use the tier default" — most nodes don't need this.
    reasoning_effort_override: str | None = None


# Baselines measured from representative fixture payloads via estimate_message_tokens.
# Update after collecting runtime metrics with llm_payload_debug enabled.
LLM_NODE_BUDGETS: dict[str, LlmNodeBudget] = {
    "profile_extraction": LlmNodeBudget(
        node="profile_extraction",
        max_input_tokens=1100,
        exception_note="Query length may exceed normal budget.",
    ),
    "research_query_planning": LlmNodeBudget(
        node="research_query_planning",
        max_input_tokens=750,
    ),
    "research_react_loop": LlmNodeBudget(
        node="research_react_loop",
        max_input_tokens=3000,
        exception_note="Cumulative multi-turn budget.",
    ),
    "research_evidence_eval": LlmNodeBudget(
        node="research_evidence_eval",
        max_input_tokens=1300,
        exception_note="May be skipped deterministically.",
    ),
    "research_synthesis": LlmNodeBudget(
        node="research_synthesis",
        max_input_tokens=2600,
        exception_note="Evidence snippet settings drive budget.",
        # Heaviest STANDARD-tier call (largest input, must reconcile
        # potentially conflicting sources into structured findings) — bump
        # above the STANDARD tier's global "none" default instead of
        # promoting the whole node to the XHIGH tier/model.
        reasoning_effort_override="low",
    ),
    "fitness_planner": LlmNodeBudget(
        node="fitness_planner",
        max_input_tokens=1100,
        exception_note="Safety retry counts separately.",
    ),
    "supervisor_router": LlmNodeBudget(
        node="supervisor_router",
        max_input_tokens=1100,
        exception_note="RoutingContext is deliberately compact -- similar order of "
        "magnitude to intent_judge; grows only with agent_trail/available_agents length.",
    ),
    "ragas_judge": LlmNodeBudget(
        node="ragas_judge",
        max_input_tokens=3500,
        exception_note=(
            "Benchmark-only (core.evaluation.ragas). Multi-metric Ragas SDK run: "
            "faithfulness + answer_relevancy + context precision; with reference "
            "also context_recall + answer_correctness. Cumulative budget, not "
            "enforced via check_payload_budget since Ragas builds its own "
            "prompts internally. Estimate, not measured; see L1 step 5 in "
            "known_limitations_remediation_plan.md."
        ),
    ),
}


def check_payload_budget(node: str, messages: list, *, fail: bool = False) -> dict[str, object]:
    """Compare estimated input tokens against the node budget."""
    budget = LLM_NODE_BUDGETS.get(node)
    if budget is None:
        return {"node": node, "within_budget": True, "reason": "no_budget_defined"}
    estimated = estimate_payload_tokens(messages)
    within_budget = estimated <= budget.max_input_tokens
    result = {
        "node": node,
        "estimated_input_tokens": estimated,
        "max_input_tokens": budget.max_input_tokens,
        "within_budget": within_budget,
        "exception_note": budget.exception_note,
    }
    if fail and not within_budget:
        raise AssertionError(
            f"{node} payload exceeds budget: {estimated} > {budget.max_input_tokens}"
        )
    return result


def measure_fixture_baseline(node: str, system_prompt: str, human_payload: dict) -> int:
    """Measure fixture payload size for budget calibration."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=compact_json(human_payload)),
    ]
    return estimate_payload_tokens(messages)
