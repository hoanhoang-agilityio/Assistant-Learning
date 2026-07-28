"""Phase 0 unit tests: Supervisor Router Judge + Policy Engine, in isolation.

These test the deterministic Policy Engine directly (no live LLM calls) -- the
Router Judge is stubbed via `configure_supervisor_routing_judge`, exactly like every
other judge in this codebase (`configure_topic_scope_judge`, `configure_user_intent_judge`).
Golden scenarios here are the regression suite a Supervisor prompt change must keep
passing.
"""

from core.agents.execution_context import CapabilityResult
from core.agents.routing_context import (
    AgentDescriptor,
    GuardrailState,
    RoutingContext,
    append_agent_trail,
    summarize_agent_result,
)
from core.agents.supervisor_router_judge import (
    SupervisorRoutingJudgement,
    configure_supervisor_routing_judge,
    judge_next_route,
)
from core.capabilities.policy_engine import enforce_routing_invariants
from tests.helpers.routing import default_supervisor_routing_judge

_AVAILABLE_AGENTS = [
    AgentDescriptor(name="user", description="Profile collection and validation"),
    AgentDescriptor(name="planning", description="Goal specification"),
    AgentDescriptor(name="research", description="Evidence retrieval"),
    AgentDescriptor(name="fitness", description="Workout generation"),
    AgentDescriptor(name="verification", description="Independent validation"),
    AgentDescriptor(name="hitl", description="Human approval"),
    AgentDescriptor(name="persist", description="Persist approved artifacts"),
]


def _guardrails(**overrides) -> GuardrailState:
    base = dict(
        hop_count=0,
        max_hops=12,
        profile_complete=True,
        profile_valid=True,
        revision_count=0,
    )
    base.update(overrides)
    return GuardrailState(**base)


def _base_state(**overrides) -> dict:
    state = {
        "hop_count": 0,
        "intent": "build_plan",
        "profile_complete": True,
        "profile_valid": True,
        "approval_status": None,
        "last_capability_result": None,
    }
    state.update(overrides)
    return state


def _proposal(next_agent: str) -> SupervisorRoutingJudgement:
    return SupervisorRoutingJudgement(next_agent=next_agent, reason="test", confidence=0.9)


# --- Schema plumbing -------------------------------------------------------


def test_summarize_agent_result_drops_artifacts_and_metadata() -> None:
    result = CapabilityResult(
        request_id="12345678-1234-5678-1234-567812345678",
        capability="fitness",
        status="blocked",
        blocking_reason="Evidence needed",
        missing_information=["research_findings"],
        summary="Need research first",
        artifacts={"artifact_ready": True},
        metadata={"checks_run": ["safety"]},
    )
    summary = summarize_agent_result(result)
    assert summary.capability == "fitness"
    assert summary.status == "blocked"
    assert summary.missing_information == ["research_findings"]
    assert not hasattr(summary, "artifacts")
    assert not hasattr(summary, "metadata")


def test_append_agent_trail_caps_length() -> None:
    trail: list[str] = []
    for name in ["planning", "research", "fitness", "verification", "hitl", "persist"]:
        trail = append_agent_trail(trail, name)
    assert trail == ["research", "fitness", "verification", "hitl", "persist"]


# --- Router Judge override seam --------------------------------------------


def test_configure_supervisor_routing_judge_stub_is_used() -> None:
    configure_supervisor_routing_judge(default_supervisor_routing_judge)
    try:
        ctx = RoutingContext(
            current_agent=None,
            last_agent_result=None,
            agent_trail=[],
            available_agents=_AVAILABLE_AGENTS,
            guardrail_state=_guardrails(),
            request_summary="Build me a 4-day plan; intent=build_plan",
        )
        judgement = judge_next_route(ctx)
        assert judgement.next_agent == "planning"
    finally:
        configure_supervisor_routing_judge(None)


# --- Policy Engine: golden scenarios ---------------------------------------


def test_policy_engine_forces_fitness_right_after_planning_completes() -> None:
    """Regression: observed in production -- a verify_macros-shaped request got
    classified build_plan, Planning ran and completed, and the Router Judge then
    proposed "finish" -- ending the run with Planning's own "Goal specification
    complete." summary as the final answer, having never run Fitness at all.
    Planning's only consumer is Fitness; this must be unconditional, not a
    semantic judgment call the Router Judge can get wrong."""
    state = _base_state(
        last_capability_result={
            "capability": "planning",
            "status": "completed",
            "summary": "Goal specification complete.",
        },
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "fitness"
    assert decision.overridden is True
    assert decision.override_reason == "planning_requires_fitness"


def test_policy_engine_accepts_valid_proposal_unchanged() -> None:
    state = _base_state()
    decision = enforce_routing_invariants(state, _proposal("research"), max_hops=12)
    assert decision.next_agent == "research"
    assert decision.overridden is False


def test_policy_engine_rejects_finish_on_first_hop() -> None:
    """Regression: observed in production (Langfuse trace) -- the Router Judge
    proposed "finish" on the very first hop (no capability had run yet) for a
    verify_macros request, and nothing caught it, so the run ended having never
    actually answered the user's question. "finish" before any work is done is
    never a valid semantic call; fall back to the deterministic entry capability."""
    from core.agents.execution_context import build_execution_context

    ctx = build_execution_context(intent="verify_macros")
    state = _base_state(
        intent="verify_macros",
        last_capability_result=None,
        execution_context=ctx.model_dump(mode="json"),
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "fitness"
    assert decision.overridden is True
    assert decision.override_reason == "premature_finish"


def test_policy_engine_forces_entry_node_on_first_hop_even_when_proposal_is_not_finish() -> None:
    """Regression: for a verify_plan request ("help me check this plan..."), the Router
    Judge proposed "verification" directly on the very first hop -- a plausible-sounding
    but wrong guess from the word "check" -- skipping Fitness (execution_context's own
    deterministic entry_node) entirely. Verification then ran against a nonexistent draft
    plan and the run paused for HITL approval on that broken result; approving it would
    have failed at persist looking for fitness/final_plan.md, which only Fitness's own
    artifact-writing path ever creates. `test_policy_engine_rejects_finish_on_first_hop`
    only covers the Judge proposing "finish" on hop 1 -- this is the general case of any
    wrong proposal on hop 1, which that narrower guard didn't catch."""
    from core.agents.execution_context import build_execution_context

    ctx = build_execution_context(intent="verify_plan", has_submitted_plan=True)
    state = _base_state(
        intent="verify_plan",
        last_capability_result=None,
        execution_context=ctx.model_dump(mode="json"),
    )
    decision = enforce_routing_invariants(state, _proposal("verification"), max_hops=12)
    assert decision.next_agent == "fitness"
    assert decision.overridden is True


def test_policy_engine_forces_user_when_profile_incomplete() -> None:
    state = _base_state(profile_complete=False, profile_valid=False)
    decision = enforce_routing_invariants(state, _proposal("planning"), max_hops=12)
    assert decision.next_agent == "user"
    assert decision.overridden is True
    assert decision.override_reason == "profile_incomplete"


def test_policy_engine_profile_gate_skipped_for_fitness_question() -> None:
    """fitness_question reaches "fitness" but never needed profile data -- same
    distinction `build_execution_context` used to make per-intent, now relocated."""
    state = _base_state(intent="fitness_question", profile_complete=False, profile_valid=False)
    decision = enforce_routing_invariants(state, _proposal("fitness"), max_hops=12)
    assert decision.next_agent == "fitness"
    assert decision.overridden is False


def test_policy_engine_profile_gate_applies_to_calculate_calories() -> None:
    state = _base_state(intent="calculate_calories", profile_complete=False, profile_valid=False)
    decision = enforce_routing_invariants(state, _proposal("fitness"), max_hops=12)
    assert decision.next_agent == "user"
    assert decision.overridden is True


def test_policy_engine_forces_research_when_fitness_blocked_on_it() -> None:
    state = _base_state(
        last_capability_result={
            "capability": "fitness",
            "status": "blocked",
            "missing_information": ["research_findings"],
        }
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "research"
    assert decision.override_reason == "fitness_requires_research"


def test_policy_engine_forces_fitness_after_research_completes_for_a_build() -> None:
    state = _base_state(
        intent="build_plan",
        last_capability_result={"capability": "research", "status": "completed"},
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "fitness"
    assert decision.override_reason == "research_requires_fitness"


def test_policy_engine_forces_finish_after_bare_research_question() -> None:
    state = _base_state(
        intent="research_question",
        last_capability_result={"capability": "research", "status": "completed"},
    )
    decision = enforce_routing_invariants(state, _proposal("fitness"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.override_reason == "research_question_answered"


def test_policy_engine_forces_hitl_after_verification_completes() -> None:
    state = _base_state(
        last_capability_result={"capability": "verification", "status": "completed"},
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "hitl"
    assert decision.override_reason == "verification_requires_hitl"


def test_policy_engine_forces_finish_after_readonly_fitness_answer() -> None:
    state = _base_state(
        last_capability_result={
            "capability": "fitness",
            "status": "completed",
            "artifacts": {"verification_passed": True},
        }
    )
    decision = enforce_routing_invariants(state, _proposal("verification"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.override_reason == "fitness_answer_complete"


def test_policy_engine_forces_finish_after_persist_completes() -> None:
    state = _base_state(
        last_capability_result={"capability": "persist", "status": "completed"},
    )
    decision = enforce_routing_invariants(state, _proposal("hitl"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.override_reason == "persist_complete"


def test_policy_engine_forces_verification_before_finish() -> None:
    state = _base_state(
        last_capability_result={
            "capability": "fitness",
            "status": "completed",
            "artifacts": {"artifact_ready": True},
        }
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "verification"
    assert decision.override_reason == "artifact_requires_verification"


def test_policy_engine_forces_verification_before_persist() -> None:
    state = _base_state(
        last_capability_result={
            "capability": "fitness",
            "status": "completed",
            "artifacts": {"artifact_ready": True},
        }
    )
    decision = enforce_routing_invariants(state, _proposal("persist"), max_hops=12)
    assert decision.next_agent == "verification"


def test_policy_engine_forces_hitl_before_persist_without_approval() -> None:
    state = _base_state(approval_status=None)
    decision = enforce_routing_invariants(state, _proposal("persist"), max_hops=12)
    assert decision.next_agent == "hitl"
    assert decision.override_reason == "persist_requires_hitl_approval"


def test_policy_engine_allows_persist_when_approved() -> None:
    state = _base_state(approval_status="approved")
    decision = enforce_routing_invariants(state, _proposal("persist"), max_hops=12)
    assert decision.next_agent == "persist"
    assert decision.overridden is False


def test_policy_engine_hitl_approved_forces_persist_regardless_of_proposal() -> None:
    state = _base_state(
        last_capability_result={
            "capability": "hitl",
            "status": "completed",
            "artifacts": {"approved": True},
        }
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "persist"
    assert decision.override_reason == "hitl_approved"


def test_policy_engine_revision_requested_forces_fitness() -> None:
    state = _base_state(
        approval_status="revision_requested",
        last_capability_result={"capability": "verification", "status": "completed"},
    )
    decision = enforce_routing_invariants(state, _proposal("hitl"), max_hops=12)
    assert decision.next_agent == "fitness"
    assert decision.override_reason == "revision_requested"


def test_policy_engine_revision_requested_stops_firing_once_fitness_reprocesses() -> None:
    """Self-resetting guard: approval_status stays "revision_requested" in state
    until the *next* HITL response, but the rule must only fire once -- otherwise
    every subsequent hop after Fitness (e.g. once Verification completes and is now
    "the last result") would re-trigger it and loop back to fitness forever instead
    of reaching HITL. `agent_trail` (not just the single last hop) is what makes
    this correctly stay resolved across the whole fitness -> verification -> hitl
    tail of a revision cycle."""
    state = _base_state(
        approval_status="revision_requested",
        last_capability_result={"capability": "verification", "status": "completed"},
        agent_trail=["research", "fitness", "verification"],
    )
    decision = enforce_routing_invariants(state, _proposal("hitl"), max_hops=12)
    assert decision.next_agent == "hitl"
    assert decision.overridden is False


def test_policy_engine_failed_capability_forces_finish() -> None:
    state = _base_state(last_capability_result={"capability": "fitness", "status": "failed"})
    decision = enforce_routing_invariants(state, _proposal("verification"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.override_reason == "capability_failed"


def test_policy_engine_hitl_rejected_forces_finish() -> None:
    # invoke_hitl_node always reports "completed" (never "failed") for a rejection
    # -- the negative outcome lives in artifacts.approved, not status.
    state = _base_state(
        last_capability_result={
            "capability": "hitl",
            "status": "completed",
            "artifacts": {"approved": False},
        }
    )
    decision = enforce_routing_invariants(state, _proposal("persist"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.override_reason == "hitl_rejected"


def test_policy_engine_hop_limit_forces_finish() -> None:
    state = _base_state(hop_count=12)
    decision = enforce_routing_invariants(state, _proposal("research"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.override_reason == "hop_count_exceeded"


def test_policy_engine_corrects_hallucinated_capability() -> None:
    # Structured output already constrains next_agent to RoutingDecision's Literal
    # members, so a real LLM call can't produce an arbitrary string here -- this
    # exercises the defensive fallback directly via model_construct (bypassing
    # validation) for the case of a future Literal/registry drift.
    state = _base_state()
    hallucinated = SupervisorRoutingJudgement.model_construct(
        next_agent="nonexistent_capability", reason="test", confidence=0.9
    )
    decision = enforce_routing_invariants(state, hallucinated, max_hops=12)
    assert decision.next_agent == "hitl"
    assert decision.override_reason == "invalid_next_agent"


def test_policy_engine_finish_is_a_valid_proposal_once_work_has_been_done() -> None:
    """ "finish" isn't caught by the hallucination-guard (it's not in
    CAPABILITY_REGISTRY, but is a valid sentinel) once some capability has
    actually run -- see test_policy_engine_rejects_finish_on_first_hop for the
    complementary "no work done yet" case, which is a different, deterministic
    rejection reason. Uses "user" as the last capability since it's the one
    capability with no deterministic next-step rule of its own (unlike research/
    fitness/verification/hitl/persist, which each force a specific next hop)."""
    state = _base_state(
        last_capability_result={"capability": "user", "status": "completed"},
    )
    decision = enforce_routing_invariants(state, _proposal("finish"), max_hops=12)
    assert decision.next_agent == "finish"
    assert decision.overridden is False
