"""Deterministic Policy Engine -- validates/overrides every Supervisor Router proposal.

Business rules must never depend on LLM judgment (see docs/reports/
user_subgraph_refactor_prompt.md's prior decision on the profile-gate, which this
generalizes into a full deterministic invariant layer). The Supervisor Router Judge
proposes a next capability; this module is the sole authority on whether that
proposal is allowed to stand, and is the only place hard business rules live.

`_deterministic_next_after` is the core of this: for this app's current capability
set, almost every hop in the pipeline (planning -> fitness -> research -> fitness
-> verification -> hitl -> persist) has exactly one valid next step given what the
just-completed capability reported -- there is no genuine ambiguity for an LLM to
resolve. Two production incidents (see comments below) came from exactly this kind
of hard sequitur being left to the Router Judge's "semantic judgment" instead of
being enforced here. The Router Judge's real value is the first-hop entry decision
and anything genuinely novel (a future capability/blocking reason with more than
one valid resolution) -- not re-deciding things that were never actually in doubt.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.agents.state import OrchestrationState
from core.agents.supervisor_router_judge import RoutingDecision, SupervisorRoutingJudgement
from core.capabilities.registry import CAPABILITY_REGISTRY

# Capabilities that need a validated user profile to operate correctly. Mirrors
# what `build_execution_context` used to compute per-intent -- relocated here
# rather than reinvented, since the underlying business rule hasn't changed.
_PROFILE_REQUIRED_CAPABILITIES = frozenset({"planning", "fitness", "verification"})

# Intents that reach a profile-capable capability (namely "fitness") without
# actually needing profile data. Preserves the exact distinction
# `build_execution_context` made per-intent (fitness_question vs. calculate_calories,
# both entering "fitness").
_INTENT_SKIPS_PROFILE_GATE: frozenset[str] = frozenset({"research_question", "fitness_question"})

_FALLBACK_TARGET: RoutingDecision = "hitl"


@dataclass(frozen=True)
class PolicyDecision:
    """The final, enforced routing decision -- what actually gets used to route."""

    next_agent: RoutingDecision
    overridden: bool
    override_reason: str | None = None


def _profile_ready(state: OrchestrationState) -> bool:
    return bool(state.get("profile_complete") and state.get("profile_valid"))


def _apply_profile_gate(state: OrchestrationState, decision: PolicyDecision) -> PolicyDecision:
    """Redirect profile-required targets to ``user`` when the profile is not ready.

    Must run on the *final* decision, including entry-node and deterministic
    overrides. Those paths used to return early and skip the profile gate, which
    let Planning/Fitness run against an incomplete profile (production: Fitness
    then crashed on ``macro_targets is None``).
    """
    if decision.next_agent not in _PROFILE_REQUIRED_CAPABILITIES:
        return decision
    if state.get("intent") in _INTENT_SKIPS_PROFILE_GATE:
        return decision
    if _profile_ready(state):
        return decision
    return PolicyDecision("user", True, "profile_incomplete")


def _deterministic_next_after(state: OrchestrationState) -> tuple[RoutingDecision, str] | None:
    """The one valid next step after the just-completed capability's result, when
    one is actually known -- `None` means there's no hard rule for this case (first
    hop, or a genuinely novel situation), so the Router Judge's proposal stands.

    Each case here previously lived in `capability.py`/`executor.py` as an
    unconditional `next_request` the capability constructed for itself -- moved
    here unchanged in effect, just relocated to the single place hard rules live.
    """
    last = state.get("last_capability_result") or {}
    capability = last.get("capability")
    status = last.get("status")
    artifacts = last.get("artifacts") or {}

    if status == "failed":
        # No valid path forward for any capability's unrecoverable failure.
        return "finish", "capability_failed"

    if capability == "planning" and status == "completed":
        # Planning's only consumer is Fitness. Production incident: the Router
        # Judge proposed "finish" right after Planning completed (for a
        # verify_macros-shaped request misclassified as build_plan), ending the
        # run with Planning's own "Goal specification complete." summary as the
        # final answer -- Fitness never ran at all.
        return "fitness", "planning_requires_fitness"

    if capability == "research" and status == "completed":
        # A bare research question has nothing further to do; research feeding a
        # build/edit always continues into Fitness.
        if state.get("intent") == "research_question":
            return "finish", "research_question_answered"
        return "fitness", "research_requires_fitness"

    if capability == "fitness":
        missing = last.get("missing_information") or []
        if status == "blocked" and "research_findings" in missing:
            return "research", "fitness_requires_research"
        if status == "blocked" and "profile_biometrics" in missing:
            # Defense-in-depth when VFS profile lacks weight/height/age even if
            # orchestration flags claimed the profile was ready.
            if _profile_ready(state):
                return "fitness", "profile_ready_retry_fitness"
            return "user", "fitness_requires_profile"
        if status == "completed":
            # A freshly produced/edited artifact always needs Verification before
            # anything else; a read-only answer (verify_macros/calculate_calories/
            # verify_plan/fitness_question) has nothing left to do.
            if artifacts.get("artifact_ready"):
                return "verification", "artifact_requires_verification"
            return "finish", "fitness_answer_complete"

    if capability == "verification" and status == "completed":
        # Verification is only ever invoked in service of an eventual HITL+persist
        # cycle (see the `artifact_requires_verification` rule above) -- it always
        # continues to HITL.
        return "hitl", "verification_requires_hitl"

    if capability == "hitl" and status == "completed":
        # HITL's own outcome is a hard sequitur, not left for the Supervisor to
        # re-derive: approved always goes to persist next, anything else ends the run.
        if artifacts.get("approved"):
            return "persist", "hitl_approved"
        return "finish", "hitl_rejected"

    if capability == "persist" and status == "completed":
        return "finish", "persist_complete"

    return None


def enforce_routing_invariants(
    state: OrchestrationState,
    proposal: SupervisorRoutingJudgement,
    *,
    max_hops: int,
) -> PolicyDecision:
    """Validate/override the Supervisor's proposal. Called once per hop, after the
    Router Judge and before the graph actually routes anywhere.

    Rules are checked in priority order; the first one that applies wins.
    """
    proposed = proposal.next_agent

    hop_count = int(state.get("hop_count") or 0)
    if hop_count >= max_hops:
        return PolicyDecision("finish", True, "hop_count_exceeded")

    # No capability has run yet -- if a deterministic entry node is available
    # (`execution_context.entry_node`, computed from the classified intent in
    # Supervisor's first-entry pass), it's never a genuine judgment call for the
    # Router Judge to override. Originally this only guarded the Judge proposing
    # "finish" outright (observed in production: "finish" on hop 1 for a
    # verify_macros request, so the user's question was never answered).
    # Broadened to *any* proposal after a second incident: for "help me check
    # this plan..." (intent=verify_plan, entry_node=fitness), the Judge proposed
    # "verification" directly on hop 1 -- a plausible-sounding but wrong guess
    # from the word "check" -- skipping Fitness entirely. Verification then ran
    # against a nonexistent draft plan, still reported status="completed"
    # (missing-artifact findings, not a capability failure), and the
    # deterministic verification->hitl->persist chain paused for approval on
    # that broken result; persist would have then failed looking for
    # fitness/final_plan.md, which only Fitness's own artifact-writing path ever
    # creates. The "finish"-only check caught neither case.
    #
    # Only fires when there's an actual entry node to enforce (a real run always
    # has one set by the time any routing decision runs -- see
    # `supervisor_node`/`_classify_and_build_context`) or the proposal is
    # "finish" (the original narrower guard, preserved so ending prematurely
    # with no entry node resolved still falls back to a safe default rather
    # than being silently accepted). Everything else -- profile gate,
    # hallucination guard, etc. -- still needs to run its own checks below when
    # neither of those applies (e.g. minimal test/handoff states with no
    # `execution_context` that aren't actually describing a real hop 1).
    if state.get("last_capability_result") is None:
        entry_node = (state.get("execution_context") or {}).get("entry_node")
        if entry_node and entry_node != proposed:
            return _apply_profile_gate(state, PolicyDecision(entry_node, True, "premature_finish"))
        if entry_node is None and proposed == "finish":
            return PolicyDecision(_FALLBACK_TARGET, True, "premature_finish")

    # A revision request always targets Fitness directly -- not a semantic judgment
    # call (see core.hitl.resume.user_revision_to_replan_update, which no longer
    # threads a pending_request through a dispatcher to make this happen; this rule
    # is what actually routes it now). Self-resetting: `approval_status` stays
    # "revision_requested" in state until the user responds to the *next* HITL
    # request, so this checks `agent_trail` (not just the single last hop) for
    # whether Fitness has *already* reprocessed since the revision was requested --
    # otherwise the rule would keep re-firing on every hop after Fitness (e.g. once
    # Verification completes, "the last result wasn't Fitness" would be true again,
    # forcing Fitness a second time and looping forever instead of reaching HITL).
    if state.get("approval_status") == "revision_requested" and "fitness" not in (
        state.get("agent_trail") or []
    ):
        return _apply_profile_gate(
            state, PolicyDecision("fitness", proposed != "fitness", "revision_requested")
        )

    deterministic = _deterministic_next_after(state)
    if deterministic is not None:
        target, reason = deterministic
        return _apply_profile_gate(state, PolicyDecision(target, target != proposed, reason))

    # Defense-in-depth: catches a "persist" proposal not immediately preceded by an
    # approved HITL result (the deterministic table above already handles the
    # normal hitl->persist sequitur; this guards any other path that somehow
    # proposes persist directly).
    if proposed == "persist" and state.get("approval_status") != "approved":
        return PolicyDecision("hitl", True, "persist_requires_hitl_approval")

    if proposed != "finish" and proposed not in CAPABILITY_REGISTRY:
        return PolicyDecision(_FALLBACK_TARGET, True, "invalid_next_agent")

    return _apply_profile_gate(state, PolicyDecision(proposed, False, None))
