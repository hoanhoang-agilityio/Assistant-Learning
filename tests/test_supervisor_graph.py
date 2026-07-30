"""Supervisor graph tests for intent-driven execution."""

from core.agents.intent_judge import UserIntentJudgement, configure_user_intent_judge
from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.agents.topic_scope_judge import configure_topic_scope_judge
from core.graph.routing import route_from_supervisor
from core.vfs import VFS
from core.vfs.layout import PLAN_SUBMITTED_TEXT
from tests.helpers.classification import default_topic_scope_judge, default_user_intent_judge


def _base_state(**overrides) -> OrchestrationState:
    state: OrchestrationState = {
        "run_id": "r1",
        "thread_id": "t1",
        "user_id": "u1",
        "current_node": "supervisor",
        "query": "Build me a 4-day training plan",
        "fitness_query": None,
        "scope_result": None,
        "execution_context": None,
        "intent": None,
        "profile_complete": True,
        "profile_valid": True,
        "days_per_week_explicit": False,
        "submitted_plan_text": None,
        "active_capability": None,
        "pending_request": None,
        "capability_stack": [],
        "capability_results": {},
        "last_capability_result": None,
        "resume_capability": None,
        "verification_passed": False,
        "faithfulness_score": None,
        "hop_count": 0,
        "agent_trail": [],
        "next_agent": None,
        "waiting_for_user": False,
        "approval_status": None,
        "user_response": None,
        "revision_feedback": None,
        "revision_count": 0,
        "workspace_path": "/tmp/ws",
        "final_artifact_path": None,
        "final_response": None,
        "refusal_message": None,
        "run_complete": False,
        "steps": [],
    }
    state.update(overrides)
    return state


def test_supervisor_builds_execution_context() -> None:
    configure_topic_scope_judge(default_topic_scope_judge)
    configure_user_intent_judge(
        lambda _q: UserIntentJudgement(
            intent="build_plan",
            reason="test",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=False,
        )
    )
    updates = supervisor_node(_base_state())
    assert updates["execution_context"]["intent"] == "build_plan"
    assert updates["execution_context"]["entry_node"] == "planning"


def test_supervisor_refuses_off_topic() -> None:
    configure_topic_scope_judge(lambda _q: default_topic_scope_judge("what is the weather"))
    updates = supervisor_node(_base_state(query="what is the weather"))
    assert updates.get("run_complete") is True
    assert updates.get("refusal_message")


def test_supervisor_allows_weight_loss_macro_check_suggestion() -> None:
    """Regression: the welcome-card macro check was CLARIFY-rejected by topic_scope_judge
    because the LLM treated the weight-loss goal as background instead of recognizing
    the macro-verification ask as actionable."""
    query = (
        "I want to know if my current macros are appropriate for weight loss. "
        "I'm currently consuming 3,000 calories per day."
    )
    configure_topic_scope_judge(default_topic_scope_judge)
    configure_user_intent_judge(default_user_intent_judge)
    updates = supervisor_node(_base_state(query=query))
    assert updates.get("run_complete") is not True
    assert updates.get("refusal_message") is None
    assert updates["execution_context"]["intent"] == "verify_macros"
    assert updates["execution_context"]["entry_node"] == "fitness"


def test_route_to_user_when_profile_incomplete() -> None:
    configure_topic_scope_judge(default_topic_scope_judge)
    configure_user_intent_judge(
        lambda _q: UserIntentJudgement(
            intent="build_plan",
            reason="test",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=False,
        )
    )
    state = _base_state(profile_complete=False, profile_valid=False)
    state.update(supervisor_node(state))
    assert route_from_supervisor(state) == "user"


def test_supervisor_captures_query_as_submitted_plan_text_when_llm_detects_it(
    tmp_path,
) -> None:
    """Regression: a user who pastes their plan straight into the chat query (rather than
    the dedicated submitted_plan_text field) previously got routed to verify_plan with no
    plan text ever captured, so the Fitness capability failed with
    missing_structured_workout. Supervisor must capture state["query"] as
    submitted_plan_text itself, and persist it to VFS, whenever the intent judge flags
    mentions_submitted_plan and nothing was already supplied."""
    configure_topic_scope_judge(default_topic_scope_judge)
    plan_query = "Here's my plan: Day 1 Squat 3x5, Day 2 Bench 3x5. Is it balanced?"
    configure_user_intent_judge(
        lambda _q: UserIntentJudgement(
            intent="verify_plan",
            reason="test",
            mentions_submitted_plan=True,
            touches_goal_or_constraints=False,
        )
    )
    workspace_path = tmp_path / "ws"
    workspace_path.mkdir()
    state = _base_state(query=plan_query, workspace_path=str(workspace_path))

    updates = supervisor_node(state)

    assert updates["submitted_plan_text"] == plan_query
    assert VFS.for_run(workspace_path).read(PLAN_SUBMITTED_TEXT) == plan_query
    assert updates["execution_context"]["intent"] == "verify_plan"
    assert updates["execution_context"]["current_artifact"]["kind"] == "submitted_plan"


def test_supervisor_does_not_overwrite_already_present_submitted_plan_text(
    tmp_path,
) -> None:
    """When submitted_plan_text was already supplied explicitly (e.g. CreateRunRequest
    .submitted_plan_text), Supervisor must not clobber it with the raw chat query."""
    configure_topic_scope_judge(default_topic_scope_judge)
    configure_user_intent_judge(
        lambda _q: UserIntentJudgement(
            intent="verify_plan",
            reason="test",
            mentions_submitted_plan=True,
            touches_goal_or_constraints=False,
        )
    )
    workspace_path = tmp_path / "ws"
    workspace_path.mkdir()
    state = _base_state(
        query="Please check this plan.",
        workspace_path=str(workspace_path),
        submitted_plan_text="Day 1: Squat 3x5",
    )

    updates = supervisor_node(state)

    assert "submitted_plan_text" not in updates
    assert not VFS.for_run(workspace_path).exists(PLAN_SUBMITTED_TEXT)
