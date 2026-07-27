"""LLM structured execution plan generation for the Planning subgraph."""

from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.factory import invoke_xhigh_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.payload import compact_json
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION
from core.profile.goal_spec import GoalSpec
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.planning.utils import build_planning_payload

PlanningAgentOverride = Callable[..., ExecutionPlan]

_AGENT_OVERRIDE: PlanningAgentOverride | None = None

_PLANNING_SYSTEM_PROMPT = f"""You are a fitness research planning agent.

Given a validated user profile, original query, request type, and constraints, produce
a structured execution plan of research tasks that downstream agents will use to gather
evidence before synthesizing a training or macro plan.

Rules:
- Tailor every task to the user's goal, activity level, and constraints.
- Each task must be research-oriented (evidence retrieval), not final coaching advice.
- Include source credibility or evidence-quality verification when relevant.
- When request_type is macro_calculation, include macro-calculation research tasks.
- Order tasks logically: foundational evidence first, verification last.
- plan_markdown must summarize goal, constraints, ordered tasks, and overall rationale.
- Keep plan_markdown concise (roughly 200-600 words); use bullet points, not long prose.
- Do not invent profile fields not present in the input.
- Return 3 distinct, non-overlapping tasks.
- When revision_feedback is present, address every user concern explicitly in tasks and rationale.
- {JSON_ONLY_INSTRUCTION}"""


def configure_planning_agent(override: PlanningAgentOverride | None) -> None:
    """Override the planning agent (used in tests)."""
    global _AGENT_OVERRIDE
    _AGENT_OVERRIDE = override


def is_planning_agent_overridden() -> bool:
    """Return True when tests or callers have configured a planning agent override."""
    return _AGENT_OVERRIDE is not None


def normalize_execution_plan(plan: ExecutionPlan) -> ExecutionPlan:
    """Sort tasks by order and re-index to a contiguous 1..N sequence."""
    if not plan.tasks:
        raise ValueError("Execution plan must contain at least one task")
    sorted_tasks = sorted(plan.tasks, key=lambda task: task.order)
    normalized_tasks = [
        PlanTask(order=index, task=task.task, rationale=task.rationale)
        for index, task in enumerate(sorted_tasks, start=1)
    ]
    return plan.model_copy(update={"tasks": normalized_tasks})


def generate_execution_plan(
    *,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    query: str,
    request_type: str | None,
    constraints: dict[str, Any],
    revision_feedback: str | None = None,
) -> ExecutionPlan:
    """Generate a structured execution plan via LLM structured output.

    `goal_spec` must be derived by the caller (`generate_plan`) -- passed through, not
    recomputed here.
    """
    if _AGENT_OVERRIDE is not None:
        return normalize_execution_plan(
            _AGENT_OVERRIDE(
                profile=profile,
                query=query,
                request_type=request_type,
                constraints=constraints,
            )
        )
    payload = build_planning_payload(
        profile=profile,
        goal_spec=goal_spec,
        query=query,
        request_type=request_type,
        constraints=constraints,
        revision_feedback=revision_feedback,
    )
    token = set_llm_metrics_node("planning_agent")
    try:
        plan = invoke_xhigh_structured_output(
            ExecutionPlan,
            [
                SystemMessage(content=_PLANNING_SYSTEM_PROMPT),
                HumanMessage(content=compact_json(payload)),
            ],
            prompt_cache_key="planning_agent",
        )
    finally:
        reset_llm_metrics_node(token)
    return normalize_execution_plan(plan)
