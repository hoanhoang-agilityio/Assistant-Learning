from pathlib import Path

import pytest
from langgraph.graph import END

from core.agents.intent_judge import UserIntentJudgement, configure_user_intent_judge
from core.agents.request_type_judge import RequestTypeJudgement, configure_request_type_judge
from core.agents.state import OrchestrationState, ScopeResult
from core.agents.supervisor import supervisor_node
from core.agents.tools import (
    OFF_TOPIC_REFUSAL_MESSAGE,
    REQUEST_TYPE_DOMAIN_OVERRIDES,
    SUBMITTED_PLAN_MISSING_MESSAGE,
    VERIFY_WORKFLOW_UNAVAILABLE_MESSAGE,
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


def _configure_generate_classification_stubs() -> None:
    configure_topic_scope_judge(
        lambda _query: TopicScopeJudgement(
            decision="ALLOW",
            requests=[
                ScopeRequest(text=_query, action_type="training_plan", supported=True),
            ],
            reason="Test stub.",
        )
    )
    configure_request_type_judge(
        lambda _query: RequestTypeJudgement(request_type="training_plan", reason="Test stub.")
    )


def test_supervisor_node_flag_off_matches_flag_on_generate_apart_from_execution_plan(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 3 (implementation_plan.md, phase_3_technical_spec.md): supervisor_node now
    reads run_execution_plan_enabled. The invariant is no longer "output is byte-identical
    regardless of the flag" (superseded from Phase 2's version of this test) -- it's "every
    field except execution_plan is identical, and execution_plan is populated only when the
    resolved workflow is GenerateWorkflow" (the default intent-judge stub always resolves to
    generate, per tests/helpers/classification.py)."""
    _configure_generate_classification_stubs()

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "false")
    get_settings.cache_clear()
    result_off = supervisor_node(dict(initial_state))

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    get_settings.cache_clear()
    result_on = supervisor_node(dict(initial_state))

    assert "execution_plan" not in result_off
    assert result_on["execution_plan"] == {
        "user_intent": "generate",
        "workflow": "GenerateWorkflow",
        "ordered_domains": ["planning", "research", "fitness", "verify"],
        "fitness_mode": "generate",
        "verification_strategy": "FULL",
    }
    result_on_without_plan = {k: v for k, v in result_on.items() if k != "execution_plan"}
    assert result_off == result_on_without_plan


def test_supervisor_node_withholds_execution_plan_for_edit_workflow(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EditWorkflow/EditWithReplanWorkflow are still Phase 6's concern -- unaffected by
    Phase 4 -- so an edit classification must still fall back to legacy routing exactly as
    if the flag were off, with no REFUSED/execution_plan of any kind."""
    _configure_generate_classification_stubs()
    configure_user_intent_judge(
        lambda _query: UserIntentJudgement(
            user_intent="edit",
            reason="Test stub.",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=False,
        )
    )

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "false")
    get_settings.cache_clear()
    result_off = supervisor_node(dict(initial_state))

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    get_settings.cache_clear()
    result_on = supervisor_node(dict(initial_state))

    assert "execution_plan" not in result_off
    assert "execution_plan" not in result_on
    assert result_off == result_on


def _configure_verify_classification(mentions_submitted_plan: bool = True) -> None:
    configure_user_intent_judge(
        lambda _query: UserIntentJudgement(
            user_intent="verify",
            reason="Test stub.",
            mentions_submitted_plan=mentions_submitted_plan,
            touches_goal_or_constraints=False,
        )
    )


def test_supervisor_node_refuses_verify_when_flag_off(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 4, Gap 2: verify_workflow_enabled off -- ends via REFUSED with the "not yet
    supported" message, not a silent fallback into plan generation."""
    _configure_generate_classification_stubs()
    _configure_verify_classification()

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("VERIFY_WORKFLOW_ENABLED", "false")
    get_settings.cache_clear()
    result = supervisor_node({**initial_state, "submitted_plan_text": "Day 1: Squat 3x5"})

    assert "execution_plan" not in result
    assert result["route_decision"] == "REFUSED"
    assert result["refusal_message"] == VERIFY_WORKFLOW_UNAVAILABLE_MESSAGE


def test_supervisor_node_refuses_verify_when_no_plan_anywhere(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 4, Gap 3: flag on, no dedicated submitted_plan_text, AND the intent judge
    found no plan referenced inline in `query` either -- fails closed, with a distinct
    message from Gap 2's. This is the only combination that should still REFUSED; it's the
    regression guard for "no plan provided" (neither channel has one)."""
    _configure_generate_classification_stubs()
    _configure_verify_classification(mentions_submitted_plan=False)

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("VERIFY_WORKFLOW_ENABLED", "true")
    get_settings.cache_clear()
    result = supervisor_node({**initial_state, "submitted_plan_text": "   "})

    assert "execution_plan" not in result
    assert result["route_decision"] == "REFUSED"
    assert result["refusal_message"] == SUBMITTED_PLAN_MISSING_MESSAGE


def test_supervisor_node_stores_execution_plan_for_verify_when_fully_enabled(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dedicated submitted_plan_text case: both flags on and plan text present via the
    dedicated field -- VerifyExternalWorkflow is genuinely reachable, and submitted_plan_text
    passes through unchanged (existing behavior, unaffected by the inline-plan fallback)."""
    _configure_generate_classification_stubs()
    _configure_verify_classification()

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("VERIFY_WORKFLOW_ENABLED", "true")
    get_settings.cache_clear()
    result = supervisor_node(
        {**initial_state, "submitted_plan_text": "Day 1: Squat 3x5\nDay 2: Bench 3x5"}
    )

    assert result.get("route_decision") != "REFUSED"
    assert "submitted_plan_text" not in result  # unchanged from the input state, not rewritten
    assert result["execution_plan"] == {
        "user_intent": "verify",
        "workflow": "VerifyExternalWorkflow",
        "ordered_domains": ["fitness", "verify"],
        "fitness_mode": "evaluate",
        "verification_strategy": "EXTERNAL_PLAN",
    }


def test_supervisor_node_backfills_submitted_plan_text_from_inline_query(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inline workout plan in query: no dedicated submitted_plan_text was sent, but the
    intent judge flags mentions_submitted_plan=True (the plan was pasted directly into the
    chat message) -- the raw query should be backfilled into submitted_plan_text and routing
    should proceed into VerifyExternalWorkflow instead of refusing. Regression test for the
    "plan pasted inline in query" bug: the query itself is never touched or rewritten, it's
    only copied verbatim (design review F2 -- no LLM transcription happens here)."""
    inline_query = (
        "i want to gain weight, help me verify this plan if there is nothing wrong, "
        "correct them\n\nDay 1 -- Upper Push/Pull\nBarbell Bench Press: 4 x 6-8"
    )
    _configure_generate_classification_stubs()
    _configure_verify_classification(mentions_submitted_plan=True)

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("VERIFY_WORKFLOW_ENABLED", "true")
    get_settings.cache_clear()
    result = supervisor_node({**initial_state, "query": inline_query, "submitted_plan_text": None})

    assert result.get("route_decision") != "REFUSED"
    assert result["submitted_plan_text"] == inline_query
    assert result["execution_plan"] == {
        "user_intent": "verify",
        "workflow": "VerifyExternalWorkflow",
        "ordered_domains": ["fitness", "verify"],
        "fitness_mode": "evaluate",
        "verification_strategy": "EXTERNAL_PLAN",
    }


def test_routing_identical_regardless_of_flag_for_generate_classification(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The routing-level invariant Phase 3 actually promises: whatever supervisor_node's
    raw output looks like, route_from_supervisor's decision for the first hop is identical
    whether execution_plan is present (flag on) or absent (flag off)."""
    _configure_generate_classification_stubs()

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "false")
    get_settings.cache_clear()
    result_off = supervisor_node(dict(initial_state))
    state_off: OrchestrationState = {**initial_state, **result_off}

    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    get_settings.cache_clear()
    result_on = supervisor_node(dict(initial_state))
    state_on: OrchestrationState = {**initial_state, **result_on}

    assert route_from_supervisor(state_off) == route_from_supervisor(state_on) == "planning"


def _plan_dict(**overrides: object) -> dict:
    defaults: dict[str, object] = {
        "user_intent": "generate",
        "workflow": "GenerateWorkflow",
        "ordered_domains": ["planning", "research", "fitness", "verify"],
        "fitness_mode": "generate",
        "verification_strategy": "FULL",
    }
    defaults.update(overrides)
    return defaults


def test_resolve_next_subgraph_entry_reads_execution_plan(
    initial_state: OrchestrationState,
) -> None:
    """Phase 3: resolve_next_subgraph's first-hop decision comes from
    RunExecutionPlan.ordered_domains, not affected_domains, when a plan is present -- using
    a plan whose entry domain differs from affected_domains' own first entry proves the new
    code path is actually being read, not coincidentally matching the legacy one."""
    state: OrchestrationState = {
        **initial_state,
        "current_node": "supervisor",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "execution_plan": _plan_dict(
            ordered_domains=["fitness", "verify"], fitness_mode="evaluate"
        ),
    }
    assert resolve_next_subgraph(state) == "fitness"


def test_resolve_next_subgraph_mid_pipeline_walks_execution_plan_ordered_domains(
    initial_state: OrchestrationState,
) -> None:
    state: OrchestrationState = {
        **initial_state,
        "current_node": "fitness",
        "execution_plan": _plan_dict(ordered_domains=["fitness", "verify"]),
    }
    assert resolve_next_subgraph(state) == "verification"


def test_resolve_next_subgraph_hitl_when_execution_plan_domains_exhausted(
    initial_state: OrchestrationState,
) -> None:
    state: OrchestrationState = {
        **initial_state,
        "current_node": "verification",
        "execution_plan": _plan_dict(ordered_domains=["fitness", "verify"]),
    }
    assert resolve_next_subgraph(state) == "hitl"


def test_resolve_next_subgraph_falls_back_to_affected_domains_when_plan_absent(
    initial_state: OrchestrationState,
) -> None:
    """execution_plan absent (flag off, or Gap A withheld it) -- byte-identical to
    pre-Phase-3 behavior."""
    state: OrchestrationState = {
        **initial_state,
        "current_node": "supervisor",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "execution_plan": None,
    }
    assert resolve_next_subgraph(state) == "planning"


def test_revision_requested_reads_entry_domain_from_execution_plan(
    initial_state: OrchestrationState,
) -> None:
    """A plan whose entry domain isn't "planning" proves _route_terminal_decision's
    revision_requested branch reads RunExecutionPlan.entry_domain rather than always
    returning the legacy literal."""
    state: OrchestrationState = {
        **initial_state,
        "approval_status": "revision_requested",
        "replan_count": 0,
        "execution_plan": _plan_dict(ordered_domains=["fitness", "verify"]),
        "route_decision": "COMPLETE",
        "waiting_for_user": False,
    }
    assert route_from_supervisor(state) == "fitness"


def test_revision_requested_falls_back_to_planning_when_plan_absent(
    initial_state: OrchestrationState,
) -> None:
    state: OrchestrationState = {
        **initial_state,
        "approval_status": "revision_requested",
        "replan_count": 0,
        "execution_plan": None,
        "route_decision": "COMPLETE",
        "waiting_for_user": False,
    }
    assert route_from_supervisor(state) == "planning"


def test_resolve_next_subgraph_handles_pre_phase_1_checkpoint_missing_key(
    initial_state: OrchestrationState,
) -> None:
    """Migration test: a checkpoint from before Phase 1 shipped has no execution_plan key
    at all (not even None) -- .get(), not [...], at every read site must handle this
    identically to the flag-off case, with no KeyError."""
    state = dict(initial_state)
    state["current_node"] = "supervisor"
    state["affected_domains"] = ["planning", "research", "fitness", "verify"]
    del state["execution_plan"]
    assert "execution_plan" not in state
    assert resolve_next_subgraph(state) == "planning"  # type: ignore[arg-type]


def test_routing_uses_already_populated_plan_regardless_of_live_flag_value(
    initial_state: OrchestrationState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design review F3, reconfirmed for Phase 3: flipping run_execution_plan_enabled back
    to False does not retroactively change a run whose execution_plan is already populated
    in its checkpoint -- routing reads state presence, not the live setting. Inconsequential
    for Phase 3 (every populated plan is GenerateWorkflow, routing identical to legacy
    either way), but the mechanism must be proven, not assumed."""
    state: OrchestrationState = {
        **initial_state,
        "current_node": "supervisor",
        "execution_plan": _plan_dict(),
    }
    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "false")
    get_settings.cache_clear()
    assert resolve_next_subgraph(state) == "planning"
