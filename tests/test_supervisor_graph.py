from pathlib import Path

import pytest
from langgraph.graph import END

from core.agents.request_type_judge import RequestTypeJudgement, configure_request_type_judge
from core.agents.state import OrchestrationState, ScopeResult
from core.agents.supervisor import supervisor_node
from core.agents.tools import (
    OFF_TOPIC_REFUSAL_MESSAGE,
    REQUEST_TYPE_DOMAIN_OVERRIDES,
    check_topic_scope,
    classify_request,
    refusal_message_for,
)
from core.agents.topic_scope_judge import (
    ScopeRequest,
    TopicScopeJudgement,
    configure_topic_scope_judge,
)
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
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="ALLOW",
            requests=[
                ScopeRequest(
                    text="Create a 4-day training plan",
                    action_type="training_plan",
                    supported=True,
                )
            ],
            reason="Training request.",
        )
    )
    result = check_topic_scope("Create a 4-day training plan")
    assert result.decision == "ALLOW"
    assert refusal_message_for(result) is None
    assert result.unsupported_requests == []
    assert [r.text for r in result.supported_requests] == ["Create a 4-day training plan"]


def test_check_topic_scope_flags_off_topic_query() -> None:
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="REJECT",
            requests=[
                ScopeRequest(
                    text="What's the capital of France?",
                    action_type="general_knowledge",
                    supported=False,
                )
            ],
            reason="Trivia question.",
        )
    )
    result = check_topic_scope("What's the capital of France?")
    assert result.decision == "REJECT"
    assert refusal_message_for(result) == OFF_TOPIC_REFUSAL_MESSAGE


def test_check_topic_scope_flags_clarify_as_off_topic_with_distinct_message() -> None:
    """CLARIFY behaves like REJECT at the routing level (blocks, run terminates) but
    must surface a clarification-specific message, not the generic off-topic refusal."""
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="CLARIFY",
            requests=[],
            reason="No concrete actionable request yet.",
        )
    )
    result = check_topic_scope("Help me.")
    assert result.decision == "CLARIFY"
    message = refusal_message_for(result)
    assert message
    assert message != OFF_TOPIC_REFUSAL_MESSAGE


def test_check_topic_scope_rescues_query_without_obvious_keyword() -> None:
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="ALLOW",
            requests=[
                ScopeRequest(
                    text="Why am I always sore afterwards?",
                    action_type="recovery_guidance",
                    supported=True,
                )
            ],
            reason="Asking about post-workout recovery.",
        )
    )
    result = check_topic_scope("Why am I always sore afterwards?")
    assert result.decision == "ALLOW"
    assert refusal_message_for(result) is None


def test_check_topic_scope_rejects_fitness_context_wrapping_an_out_of_scope_ask() -> None:
    """The exact bug case from the report: fitness context ("train at the beach") wraps
    an out-of-scope weather lookup. "train at the beach" is background, not a request,
    so there is exactly one actionable request (the weather lookup) and it's
    unsupported -- this must REJECT, not silently continue to planning with the full
    query, and must NOT be treated as mixed intent."""
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="REJECT",
            requests=[
                ScopeRequest(
                    text="give me the weather of Danang city",
                    action_type="weather_lookup",
                    supported=False,
                )
            ],
            reason="Only actionable request is a weather lookup; 'train at the beach' is context, not a request.",
        )
    )
    result = check_topic_scope("I want to train at the beach, give me the weather of Danang city")
    assert result.decision == "REJECT"
    assert result.supported_requests == []
    assert refusal_message_for(result) == OFF_TOPIC_REFUSAL_MESSAGE


def test_check_topic_scope_two_unrelated_asks_in_one_message() -> None:
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="MIXED",
            requests=[
                ScopeRequest(
                    text="write me a Python script to scrape Instagram",
                    action_type="coding",
                    supported=False,
                ),
                ScopeRequest(
                    text="give me a beginner strength training routine",
                    action_type="training_plan",
                    supported=True,
                ),
            ],
            reason="Two unrelated asks: coding help and a training routine.",
        )
    )
    result = check_topic_scope(
        "Can you write me a Python script to scrape Instagram, and also give me a "
        "beginner strength training routine?"
    )
    assert result.decision == "MIXED"
    # MIXED terminates the run (see supervisor_node) -- but both parts must remain
    # available on scope_result for logging/UI, never silently discarded.
    assert [r.text for r in result.supported_requests] == [
        "give me a beginner strength training routine"
    ]
    assert [r.text for r in result.unsupported_requests] == [
        "write me a Python script to scrape Instagram"
    ]
    message = refusal_message_for(result)
    assert "beginner strength training routine" in message
    assert "Python script to scrape Instagram" in message


def test_supervisor_node_refuses_off_topic_query(initial_state: OrchestrationState) -> None:
    state = {**initial_state, "query": "Write me a poem about the ocean"}
    updates = supervisor_node(state)
    assert updates["route_decision"] == "REFUSED"
    assert updates["refusal_message"]
    assert "request_type" not in updates
    # query is never mutated, and fitness_query is only ever set on ALLOW.
    assert "query" not in updates
    assert "fitness_query" not in updates
    assert updates["scope_result"]["decision"] == "REJECT"


def test_supervisor_node_does_not_refuse_fitness_query(
    initial_state: OrchestrationState,
) -> None:
    updates = supervisor_node(initial_state)
    assert updates.get("route_decision") != "REFUSED"
    assert updates["request_type"] == "training_plan"
    # query itself is never touched -- fitness_query is the copy planning consumes.
    assert "query" not in updates
    assert updates["fitness_query"] == initial_state["query"]
    assert updates["scope_result"]["decision"] == "ALLOW"


def test_supervisor_node_blocks_fitness_context_wrapping_an_out_of_scope_ask(
    initial_state: OrchestrationState,
) -> None:
    """The beach/weather bug case at the supervisor level: "train at the beach" is
    context, not a request, so the only actionable request is the unsupported weather
    lookup -- the supervisor must REFUSE, not silently continue to planning with the
    full original query."""
    beach_weather_query = "I want to train at the beach, give me the weather of Danang city"
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="REJECT",
            requests=[
                ScopeRequest(
                    text="give me the weather of Danang city",
                    action_type="weather_lookup",
                    supported=False,
                )
            ],
            reason="Only actionable request is a weather lookup; 'train at the beach' is context.",
        )
    )
    state = {**initial_state, "query": beach_weather_query}
    updates = supervisor_node(state)
    assert updates["route_decision"] == "REFUSED"
    assert updates["refusal_message"]
    assert "request_type" not in updates
    assert "query" not in updates
    assert "fitness_query" not in updates


def test_supervisor_node_blocks_mixed_intent_query_instead_of_continuing_with_partial_query(
    initial_state: OrchestrationState,
) -> None:
    """Mixed intent (two genuinely separate asks) must terminate the run immediately --
    NOT silently continue to classification/planning using only the supported part.
    Routing depends solely on scope_result.decision; MIXED is one of the three terminal
    decisions alongside REJECT/CLARIFY. The unsupported part must still be recoverable
    from scope_result for logging/UI even though the run stops here."""
    mixed_query = (
        "Can you write me a Python script to scrape Instagram, and also give me a "
        "beginner strength training routine?"
    )
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="MIXED",
            requests=[
                ScopeRequest(
                    text="write me a Python script to scrape Instagram",
                    action_type="coding",
                    supported=False,
                ),
                ScopeRequest(
                    text="give me a beginner strength training routine",
                    action_type="training_plan",
                    supported=True,
                ),
            ],
            reason="Two unrelated asks: coding help and a training routine.",
        )
    )
    state = {**initial_state, "query": mixed_query}
    updates = supervisor_node(state)
    assert updates["route_decision"] == "REFUSED"
    assert updates["refusal_message"]
    assert "request_type" not in updates
    assert "query" not in updates
    assert "fitness_query" not in updates
    # Persisted as a plain dict (see OrchestrationState.scope_result's docstring) --
    # a reader that wants the typed object back re-validates it at the boundary.
    scope_result_dict = updates["scope_result"]
    assert scope_result_dict["decision"] == "MIXED"
    scope_result = ScopeResult.model_validate(scope_result_dict)
    assert [r.text for r in scope_result.unsupported_requests] == [
        "write me a Python script to scrape Instagram"
    ]
    assert [r.text for r in scope_result.supported_requests] == [
        "give me a beginner strength training routine"
    ]


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
    result = classify_request("Create a 4-day training plan")
    assert result["request_type"] == "training_plan"
    assert result["affected_domains"] == ["planning", "research", "fitness", "verify"]


def test_classify_request_uses_judge_verdict_directly() -> None:
    configure_request_type_judge(
        lambda _query: RequestTypeJudgement(
            request_type="endurance", reason="Asking about race pacing."
        )
    )
    result = classify_request("How should I pace my next race?")
    assert result["request_type"] == "endurance"


def test_request_type_domain_overrides_is_empty_by_construction() -> None:
    # No request_type is currently known to be safe to narrow (see Issue 2
    # part 2 in the remediation plan) -- populating this without also
    # updating planning_agent.py's prompt would be a correctness regression.
    assert REQUEST_TYPE_DOMAIN_OVERRIDES == {}


def test_classify_request_narrows_domains_flag_defaults_off() -> None:
    assert get_settings().classify_request_narrows_domains is False


def test_classify_request_ignores_override_map_when_flag_off(monkeypatch) -> None:
    monkeypatch.setitem(REQUEST_TYPE_DOMAIN_OVERRIDES, "macro_calculation", ["planning"])
    result = classify_request("Calculate my macros")
    assert result["affected_domains"] == ["planning", "research", "fitness", "verify"]


def test_classify_request_applies_override_map_when_flag_on(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "classify_request_narrows_domains", True)
    monkeypatch.setitem(REQUEST_TYPE_DOMAIN_OVERRIDES, "macro_calculation", ["planning"])
    result = classify_request("Calculate my macros")
    assert result["affected_domains"] == ["planning"]


def test_resolve_next_subgraph_routes_to_planning(initial_state: OrchestrationState) -> None:
    classified = classify_request(initial_state["query"])
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
    classified = classify_request(initial_state["query"])
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
