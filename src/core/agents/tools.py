import logging

from langchain_core.tools import BaseTool, tool

from core.agents.rerun import partial_rerun_decision_data
from core.agents.state import AffectedDomain, OrchestrationState, RequestType
from core.agents.topic_scope_judge import judge_topic_scope
from core.config.settings import get_settings
from core.hitl.utils import hitl_control_data
from core.persist.utils import persist_trigger_data

logger = logging.getLogger(__name__)

# Broad allowlist for the topic-scope guardrail (check_topic_scope): if a
# query matches none of these, it's treated as outside the fitness/nutrition
# domain and refused before classification/routing. Intentionally broad
# (favors false negatives over blocking real fitness questions phrased in
# unusual ways) since this is a coarse pre-check, not a full classifier.
FITNESS_TOPIC_KEYWORDS: tuple[str, ...] = (
    "workout",
    "exercise",
    "training",
    "train ",
    "gym",
    "fitness",
    "muscle",
    "strength",
    "cardio",
    "endurance",
    "hypertrophy",
    "powerlifting",
    "1rm",
    "rep ",
    "reps",
    "set ",
    "sets",
    "routine",
    "regimen",
    "diet",
    "nutrition",
    "macro",
    "calorie",
    "protein",
    "carb",
    "fat loss",
    "weight loss",
    "lose weight",
    "bulk",
    "cutting",
    "cut ",
    "recovery",
    "stretch",
    "mobility",
    "flexibility",
    "yoga",
    "running",
    "marathon",
    "jog",
    "lift",
    "lifting",
    "squat",
    "deadlift",
    "bench press",
    "supplement",
    "injury",
    "warm up",
    "warmup",
    "cool down",
    "hydration",
    "bodyweight",
    "hiit",
    "crossfit",
    "pilates",
    "sore",
    "soreness",
    "physique",
)

OFF_TOPIC_REFUSAL_MESSAGE = (
    "I'm your fitness planning assistant, so I can only help with "
    "training, workouts, nutrition/macros, and related fitness goals. "
    "Could you rephrase your question around a fitness goal, like a "
    "workout plan, macro targets, or training advice?"
)

REQUEST_TYPE_KEYWORDS: list[tuple[RequestType, tuple[str, ...]]] = [
    ("fat_loss", ("lose weight", "fat loss", "cutting", "cut ")),
    ("muscle_gain", ("muscle gain", "bulk", "hypertrophy", "build muscle")),
    ("macro_calculation", ("macro", "calories", "protein", "macros")),
    ("strength", ("strength", "powerlifting", "1rm")),
    ("endurance", ("endurance", "marathon", "cardio")),
    ("training_plan", ("training plan", "workout plan", "program")),
]

DEFAULT_AFFECTED_DOMAINS: list[AffectedDomain] = [
    "planning",
    "research",
    "fitness",
    "verify",
]

# Per-request_type narrower domain set, used only when
# settings.classify_request_narrows_domains is true. Empty by construction:
# no request_type is currently known to be safe to narrow (e.g.
# macro_calculation still needs "research" per planning_agent.py's prompt),
# so populating this without also updating that prompt would cause the
# planning agent to plan work the pipeline then never runs. See
# docs/reports/known_limitations_remediation_plan.md, "Issue 2 (part 2)".
REQUEST_TYPE_DOMAIN_OVERRIDES: dict[RequestType, list[AffectedDomain]] = {}


@tool
def read_global_state(state: OrchestrationState) -> dict:
    """Read current orchestration state."""
    return {
        "run_id": state["run_id"],
        "thread_id": state["thread_id"],
        "current_node": state["current_node"],
        "query": state["query"],
        "request_type": state["request_type"],
        "affected_domains": state["affected_domains"],
        "route_decision": state["route_decision"],
        "retry_count": state["retry_count"],
        "replan_count": state["replan_count"],
        "verification_passed": state["verification_passed"],
        "faithfulness_score": state["faithfulness_score"],
        "waiting_for_user": state["waiting_for_user"],
        "approval_status": state["approval_status"],
        "workspace_path": state["workspace_path"],
        "final_artifact_path": state["final_artifact_path"],
        "steps": state.get("steps") or [],
        "approved_tools": state.get("approved_tools") or [],
        "pending_tool": state.get("pending_tool"),
    }


@tool
def check_topic_scope(query: str) -> dict:
    """Flag queries outside the fitness/nutrition domain (keyword pre-check + optional LLM fallback)."""
    query_lower = query.lower()
    is_off_topic = not any(keyword in query_lower for keyword in FITNESS_TOPIC_KEYWORDS)

    if is_off_topic and get_settings().topic_scope_llm_fallback_enabled:
        try:
            judgement = judge_topic_scope(query)
            is_off_topic = not judgement.is_fitness_related
        except Exception:
            # Fail safe to the keyword verdict (refuse) rather than let a
            # judge/API outage either block every off-topic-looking query
            # from ever being rescued, or crash the run.
            logger.warning(
                "topic_scope_judge fallback failed; using keyword verdict", exc_info=True
            )

    return {
        "is_off_topic": is_off_topic,
        "refusal_message": OFF_TOPIC_REFUSAL_MESSAGE if is_off_topic else None,
    }


@tool
def classify_request(query: str) -> dict:
    """Classify request into request_type and affected_domains."""
    query_lower = query.lower()
    request_type: RequestType = "general_fitness"

    for candidate_type, keywords in REQUEST_TYPE_KEYWORDS:
        if any(keyword in query_lower for keyword in keywords):
            request_type = candidate_type
            break

    affected_domains = list(DEFAULT_AFFECTED_DOMAINS)
    if get_settings().classify_request_narrows_domains:
        override = REQUEST_TYPE_DOMAIN_OVERRIDES.get(request_type)
        if override is not None:
            affected_domains = list(override)

    return {
        "request_type": request_type,
        "affected_domains": affected_domains,
    }


@tool
def partial_rerun_decision(
    verification_report: dict,
    retry_count: int,
    replan_count: int,
) -> dict:
    """Select FIX_REASONING, REPLAN, or RERESEARCH target for partial rerun."""
    return partial_rerun_decision_data(verification_report, retry_count, replan_count)


@tool
def hitl_control(
    waiting_for_user: bool,
    approval_status: str | None,
    user_response: str | None,
) -> dict:
    """Pause, resume, or reject workflow based on HITL status."""
    return hitl_control_data(waiting_for_user, approval_status, user_response)


@tool
def persist_trigger(
    verification_passed: bool,
    faithfulness_score: float | None,
    approval_status: str | None,
) -> dict:
    """Trigger PERSIST_RESULTS after COMPLETE and user approval."""
    return persist_trigger_data(verification_passed, faithfulness_score, approval_status)


SUPERVISOR_TOOLS: list[BaseTool] = [
    read_global_state,
    check_topic_scope,
    classify_request,
    partial_rerun_decision,
    hitl_control,
    persist_trigger,
]
