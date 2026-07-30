from pathlib import Path
from typing import Any

from core.adapters.vfs import VFS
from core.adapters.vfs.layout import FITNESS_WORKOUT, PLAN_SUBMITTED_TEXT
from core.config.settings import get_settings
from core.orchestration.agents.intent_judge import judge_user_intent
from core.orchestration.agents.supervisor_routing import run_supervisor_routing_decision
from core.orchestration.agents.tools import check_topic_scope, refusal_message_for
from core.orchestration.state import OrchestrationState
from core.shared.execution_context import build_execution_context


def _classify_and_build_context(state: OrchestrationState) -> dict[str, Any]:
    """First-entry-only: topic guard, intent classification, execution context."""
    scope_result = check_topic_scope(state["query"])
    if scope_result.decision != "ALLOW":
        return {
            "scope_result": scope_result.model_dump(),
            "refusal_message": refusal_message_for(scope_result),
            "run_complete": True,
        }

    judgement = judge_user_intent(state["query"])
    workspace = Path(state["workspace_path"])
    vfs = VFS.for_run(workspace)
    submitted_plan_text = (state.get("submitted_plan_text") or "").strip()
    has_submitted_plan = bool(submitted_plan_text or vfs.exists(PLAN_SUBMITTED_TEXT))
    has_existing_plan = vfs.exists(FITNESS_WORKOUT)

    # judgement.mentions_submitted_plan means the user pasted their plan straight into the
    # chat query rather than the dedicated submitted_plan_text channel (e.g. CreateRunRequest
    # .submitted_plan_text was never populated). Capture the query itself as the plan text
    # here -- the only point in the run where that signal is available -- and persist it to
    # VFS so it survives every later resume without the user having to resubmit it.
    if judgement.mentions_submitted_plan and not has_submitted_plan:
        submitted_plan_text = state["query"]
        vfs.write(PLAN_SUBMITTED_TEXT, submitted_plan_text)
        has_submitted_plan = True

    ctx = build_execution_context(
        intent=judgement.intent,
        touches_goal_or_constraints=judgement.touches_goal_or_constraints,
        has_submitted_plan=has_submitted_plan,
        has_existing_plan=has_existing_plan,
    )
    updates: dict[str, Any] = {
        "scope_result": scope_result.model_dump(),
        "fitness_query": state["query"],
        "execution_context": ctx.model_dump(mode="json"),
        "intent": judgement.intent,
        "current_node": "supervisor",
    }
    if submitted_plan_text and submitted_plan_text != (state.get("submitted_plan_text") or ""):
        updates["submitted_plan_text"] = submitted_plan_text
    return updates


def supervisor_node(state: OrchestrationState) -> dict:
    """Topic guard, intent classification, execution context, and the hybrid
    Supervisor routing decision (Router Judge proposal + Policy Engine
    enforcement -- see `run_supervisor_routing_decision`). Runs on *every*
    invocation, not just the first entry: this is the single node every
    capability returns to (see `core.orchestration.graph.builder`), so the routing decision
    made here is what decides every hop in the graph, not just the first one.
    """
    updates: dict[str, Any] = {}
    if state.get("execution_context") is None:
        first_entry = _classify_and_build_context(state)
        if first_entry.get("run_complete"):
            return first_entry
        updates.update(first_entry)

    settings = get_settings()
    merged_state: OrchestrationState = {**state, **updates}  # type: ignore[typeddict-item]
    updates.update(
        run_supervisor_routing_decision(
            merged_state,
            max_hops=settings.supervisor_max_hops,
            max_verification_retry_attempts=settings.max_verification_retry_attempts,
        )
    )

    return updates
