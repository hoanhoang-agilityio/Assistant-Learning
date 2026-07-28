"""Integration tests: `supervisor_node` wired to the Router Judge + Policy Engine.
Confirms the routing decision runs end-to-end (Router Judge stub -> Policy Engine
-> state update -> `route_from_supervisor`) on every invocation -- there is no
flag; this is the graph's only routing path (see docs/reports plan)."""

from langgraph.graph import END

from core.agents.intent_judge import UserIntentJudgement, configure_user_intent_judge
from core.agents.supervisor import supervisor_node
from core.agents.supervisor_router_judge import (
    SupervisorRoutingJudgement,
    configure_supervisor_routing_judge,
)
from core.agents.topic_scope_judge import configure_topic_scope_judge
from core.graph.routing import route_from_supervisor
from tests.helpers.classification import default_topic_scope_judge
from tests.test_supervisor_graph import _base_state


def _configure_build_plan_intent() -> None:
    configure_topic_scope_judge(default_topic_scope_judge)
    configure_user_intent_judge(
        lambda _q: UserIntentJudgement(
            intent="build_plan",
            reason="test",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=False,
        )
    )


def test_supervisor_node_produces_routing_decision_on_first_entry(tmp_path) -> None:
    _configure_build_plan_intent()
    configure_supervisor_routing_judge(
        lambda ctx: SupervisorRoutingJudgement(
            next_agent="planning", reason="entry", confidence=1.0
        )
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = _base_state(workspace_path=str(workspace))

    updates = supervisor_node(state)

    assert updates["next_agent"] == "planning"
    assert updates["hop_count"] == 1
    assert updates["agent_trail"] == []  # no capability has run yet on the very first hop
    state.update(updates)
    assert route_from_supervisor(state) == "planning"


def test_supervisor_routing_finish_maps_to_end_and_sets_run_complete(tmp_path) -> None:
    configure_topic_scope_judge(default_topic_scope_judge)
    configure_user_intent_judge(
        lambda _q: UserIntentJudgement(
            intent="research_question",
            reason="test",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=False,
        )
    )
    configure_supervisor_routing_judge(
        lambda ctx: SupervisorRoutingJudgement(next_agent="finish", reason="done", confidence=1.0)
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = _base_state(
        workspace_path=str(workspace),
        query="What does research say about HIIT?",
        # Simulates Research having already completed and answered the question --
        # "finish" is only a legitimate proposal once some capability has actually
        # run (see the Policy Engine's premature_finish rule, which rejects "finish"
        # as the very first hop before any work has been done).
        last_capability_result={
            "request_id": "12345678-1234-5678-1234-567812345678",
            "capability": "research",
            "status": "completed",
            "summary": "HIIT is effective for fat loss.",
            "artifacts": {},
        },
    )

    updates = supervisor_node(state)

    assert updates["next_agent"] == "finish"
    assert updates["run_complete"] is True
    state.update(updates)
    assert route_from_supervisor(state) == END


def test_supervisor_node_policy_engine_overrides_bad_proposal(tmp_path) -> None:
    """Router Judge proposes "planning" straight away, but profile is incomplete --
    the Policy Engine must override to "user" regardless of the LLM's proposal."""
    _configure_build_plan_intent()
    configure_supervisor_routing_judge(
        lambda ctx: SupervisorRoutingJudgement(
            next_agent="planning", reason="entry", confidence=1.0
        )
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = _base_state(workspace_path=str(workspace), profile_complete=False, profile_valid=False)

    updates = supervisor_node(state)

    assert updates["next_agent"] == "user"
    state.update(updates)
    assert route_from_supervisor(state) == "user"
