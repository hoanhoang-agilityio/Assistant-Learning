from pathlib import Path

import pytest
from langgraph.graph import END

from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.agents.tools import (
    REQUEST_TYPE_DOMAIN_OVERRIDES,
    check_topic_scope,
    classify_request,
    read_global_state,
)
from core.agents.topic_scope_judge import TopicScopeJudgement, configure_topic_scope_judge
from core.config.settings import get_settings
from core.graph.builder import build_graph
from core.graph.routing import resolve_next_subgraph, route_from_supervisor
from core.graph.run import create_initial_state
from core.profile.extraction import configure_profile_extractor
from core.profile.schema import ExtractedProfile, Goal, Profile
from core.subgraphs.planning.planning_agent import configure_planning_agent
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask


@pytest.fixture
def initial_state(tmp_path: Path) -> OrchestrationState:
    state = create_initial_state(
        run_id="run-day2",
        thread_id="thread-day2",
        query="I want a 4-day training plan",
        user_profile={
            "age": 30,
            "sex": "male",
            "height_cm": 175,
            "current_weight_kg": 80.0,
            "activity_level": "gym_4x_week",
            "goal": "general_fitness",
        },
        workspace_root=tmp_path / "workspace",
    )
    # Most tests in this file exercise supervisor/routing logic downstream of profile
    # intake (now owned by the User subgraph, see tests/test_user_subgraph.py) -- simulate
    # that it already ran and validated the profile above.
    return {**state, "profile_complete": True, "profile_valid": True}


def test_check_topic_scope_allows_fitness_query() -> None:
    result = check_topic_scope.invoke({"query": "Create a 4-day training plan"})
    assert result["is_off_topic"] is False
    assert result["refusal_message"] is None


def test_check_topic_scope_flags_off_topic_query() -> None:
    result = check_topic_scope.invoke({"query": "What's the capital of France?"})
    assert result["is_off_topic"] is True
    assert result["refusal_message"]


def test_topic_scope_llm_fallback_flag_defaults_off() -> None:
    assert get_settings().topic_scope_llm_fallback_enabled is False


def test_check_topic_scope_ignores_judge_when_flag_off(monkeypatch) -> None:
    def _fail_if_called(_query: str) -> TopicScopeJudgement:
        raise AssertionError("judge should not be called when the flag is off")

    configure_topic_scope_judge(_fail_if_called)
    result = check_topic_scope.invoke({"query": "What's the capital of France?"})
    assert result["is_off_topic"] is True


def test_check_topic_scope_llm_fallback_rescues_off_topic_query(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "topic_scope_llm_fallback_enabled", True)
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            is_fitness_related=True, reason="Asking about post-workout recovery."
        )
    )
    result = check_topic_scope.invoke({"query": "Why am I always sore afterwards?"})
    assert result["is_off_topic"] is False
    assert result["refusal_message"] is None


def test_check_topic_scope_llm_fallback_confirms_off_topic_query(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "topic_scope_llm_fallback_enabled", True)
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(is_fitness_related=False, reason="Trivia question.")
    )
    result = check_topic_scope.invoke({"query": "What's the capital of France?"})
    assert result["is_off_topic"] is True
    assert result["refusal_message"]


def test_check_topic_scope_llm_fallback_fails_safe_to_keyword_verdict(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "topic_scope_llm_fallback_enabled", True)

    def _raise(_query: str) -> TopicScopeJudgement:
        raise RuntimeError("LLM outage")

    configure_topic_scope_judge(_raise)
    result = check_topic_scope.invoke({"query": "What's the capital of France?"})
    assert result["is_off_topic"] is True
    assert result["refusal_message"]


def test_supervisor_node_refuses_off_topic_query(initial_state: OrchestrationState) -> None:
    state = {**initial_state, "query": "Write me a poem about the ocean"}
    updates = supervisor_node(state)
    assert updates["route_decision"] == "REFUSED"
    assert updates["refusal_message"]
    assert "request_type" not in updates


def test_supervisor_node_does_not_refuse_fitness_query(
    initial_state: OrchestrationState,
) -> None:
    updates = supervisor_node(initial_state)
    assert updates.get("route_decision") != "REFUSED"
    assert updates["request_type"] == "training_plan"


def test_route_from_supervisor_ends_on_refused(initial_state: OrchestrationState) -> None:
    state = {
        **initial_state,
        "route_decision": "REFUSED",
        "refusal_message": "off-topic",
    }
    assert route_from_supervisor(state) == END


def test_first_invoke_refuses_off_topic_query(initial_state: OrchestrationState) -> None:
    state = {**initial_state, "query": "What's the weather like tomorrow?"}
    graph = build_graph()
    config = {"configurable": {"thread_id": state["thread_id"]}}
    result = graph.invoke(state, config)
    assert result["route_decision"] == "REFUSED"
    assert result["refusal_message"]
    assert result["request_type"] is None


def test_classify_request_detects_training_plan() -> None:
    result = classify_request.invoke(
        {
            "query": "Create a 4-day training plan",
        }
    )
    assert result["request_type"] == "training_plan"
    assert result["affected_domains"] == ["planning", "research", "fitness", "verify"]


def test_request_type_domain_overrides_is_empty_by_construction() -> None:
    # No request_type is currently known to be safe to narrow (see Issue 2
    # part 2 in the remediation plan) -- populating this without also
    # updating planning_agent.py's prompt would be a correctness regression.
    assert REQUEST_TYPE_DOMAIN_OVERRIDES == {}


def test_classify_request_narrows_domains_flag_defaults_off() -> None:
    assert get_settings().classify_request_narrows_domains is False


def test_classify_request_ignores_override_map_when_flag_off(monkeypatch) -> None:
    monkeypatch.setitem(REQUEST_TYPE_DOMAIN_OVERRIDES, "macro_calculation", ["planning"])
    result = classify_request.invoke({"query": "Calculate my macros"})
    assert result["affected_domains"] == ["planning", "research", "fitness", "verify"]


def test_classify_request_applies_override_map_when_flag_on(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "classify_request_narrows_domains", True)
    monkeypatch.setitem(REQUEST_TYPE_DOMAIN_OVERRIDES, "macro_calculation", ["planning"])
    result = classify_request.invoke({"query": "Calculate my macros"})
    assert result["affected_domains"] == ["planning"]


def test_read_global_state_returns_orchestration_fields(initial_state: OrchestrationState) -> None:
    result = read_global_state.invoke({"state": initial_state})
    assert result["run_id"] == "run-day2"
    assert result["current_node"] == "supervisor"
    assert result["workspace_path"] == initial_state["workspace_path"]


def test_resolve_next_subgraph_routes_to_planning(initial_state: OrchestrationState) -> None:
    classified = classify_request.invoke(
        {
            "query": initial_state["query"],
        }
    )
    state = {**initial_state, **classified}
    assert resolve_next_subgraph(state) == "planning"
    assert route_from_supervisor(state) == "planning"


def test_graph_compiles() -> None:
    graph = build_graph()
    assert graph is not None


def test_route_from_supervisor_redirects_to_user_when_profile_incomplete(
    initial_state: OrchestrationState,
) -> None:
    """The defensive guard: a target of planning/research/fitness with no ready profile
    redirects into the User subgraph instead."""
    classified = classify_request.invoke({"query": initial_state["query"]})
    state = {
        **initial_state,
        **classified,
        "profile_complete": False,
        "profile_valid": False,
    }
    assert resolve_next_subgraph(state) == "planning"
    assert route_from_supervisor(state) == "user"


def test_route_from_supervisor_refuses_before_profile_gate(
    initial_state: OrchestrationState,
) -> None:
    """REFUSED must short-circuit before the profile guard -- an off-topic query should
    never be redirected into profile intake."""
    state = {
        **initial_state,
        "route_decision": "REFUSED",
        "refusal_message": "off-topic",
        "profile_complete": False,
        "profile_valid": False,
    }
    assert route_from_supervisor(state) == END


def test_full_graph_pauses_at_user_node_for_incomplete_profile(tmp_path: Path) -> None:
    """A brand new run with no profile at all pauses inside the User subgraph before ever
    reaching planning -- exercised end-to-end through the compiled supervisor graph."""
    state = create_initial_state(
        run_id="run-no-profile",
        thread_id="thread-no-profile",
        query="I want a 4-day training plan",
        workspace_root=tmp_path / "workspace",
    )
    configure_profile_extractor(lambda _query: ExtractedProfile())
    graph = build_graph()
    config = {"configurable": {"thread_id": state["thread_id"]}}
    result = graph.invoke(state, config)
    assert "__interrupt__" in result
    snapshot = graph.get_state(config)
    assert snapshot.next == ("user",)


def test_first_invoke_routes_to_planning(initial_state: OrchestrationState) -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=30, sex="male", height_cm=175, current_weight_kg=80),
            goal=Goal(goal="general_fitness"),
        )
    )
    configure_planning_agent(
        lambda **_kwargs: ExecutionPlan(
            plan_rationale="Deterministic planning output for supervisor graph test.",
            tasks=[
                PlanTask(order=1, task="Research training volume", rationale="Baseline evidence."),
                PlanTask(order=2, task="Research recovery guidance", rationale="Support recovery."),
                PlanTask(
                    order=3, task="Verify source credibility", rationale="Trustworthy sources."
                ),
            ],
            plan_markdown="# Test Plan\n\nDeterministic planning output for supervisor graph test.",
        )
    )
    graph = build_graph()
    config = {"configurable": {"thread_id": initial_state["thread_id"]}}
    result = graph.invoke(
        initial_state,
        config,
        interrupt_after=["planning"],
    )
    assert result["current_node"] == "planning"
    assert result["request_type"] == "training_plan"
