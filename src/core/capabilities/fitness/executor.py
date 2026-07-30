"""Deterministic Fitness capability executor.

Implements `core.orchestration.routing.executor.CapabilityExecutor`. Swappable via
`configure_fitness_executor` for a future LLM-driven ReAct executor without
touching `capability.py` or the graph. Reports a pure AgentResult per hop
(status/blocking_reason/missing_information/summary/artifacts) -- the
Supervisor + Policy Engine (see `core.orchestration.routing.policy_engine`) decide what
runs next; this executor never threads its own `next_request`.
"""

from __future__ import annotations

from uuid import uuid4

from core.capabilities.fitness import tools as fitness_tools
from core.orchestration.agents.execution_context import CapabilityResult, ExecutionContext
from core.orchestration.agents.macro_report_judge import judge_reported_macros
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.routing.executor import CapabilityExecutor


def _missing_biometrics_result() -> CapabilityResult:
    return CapabilityResult(
        request_id=uuid4(),
        capability="fitness",
        status="blocked",
        blocking_reason="Profile biometrics required for plan generation",
        missing_information=["profile_biometrics"],
        summary="Need age, height, and weight before drafting a training plan.",
    )


def _run_build_plan(state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult:
    """Same domain sequence for build_plan/edit_plan -- the Policy Engine decides to
    route to Verification next (see `artifact_requires_verification`)."""
    workspace = state["workspace_path"]
    macros = fitness_tools.calculate_macros(workspace)
    macro_targets = macros.get("macro_targets")
    if macro_targets is None:
        # calculate_macros_data returns None when weight/height/age are missing.
        # synthesize_plan_data / the planner payload would TypeError on subscript.
        return _missing_biometrics_result()
    blueprint = fitness_tools.generate_blueprint(workspace)
    template = fitness_tools.select_template(workspace)
    workout = template.get("structured_workout")
    if workout is None:
        workout_data = fitness_tools.populate_template(workspace)
        workout = workout_data["structured_workout"]
    safety = fitness_tools.validate_plan(workspace, workout)
    if not safety["passed"]:
        return CapabilityResult(
            request_id=uuid4(),
            capability="fitness",
            status="failed",
            summary="; ".join(safety.get("feedback", [])),
        )
    draft = fitness_tools.render_plan(
        workspace,
        macro_targets=macro_targets,
        structured_workout=workout,
        plan_blueprint=blueprint["plan_blueprint"],
    )
    correlation_id = str(uuid4())
    fitness_tools.write_artifacts(
        workspace,
        macro_targets=macro_targets,
        structured_workout=workout,
        draft_plan=draft["draft_plan"],
        plan_blueprint=blueprint["plan_blueprint"],
        safety_result=safety,
        correlation_id=correlation_id,
        grounded_claims_markdown=draft.get("grounded_claims_markdown"),
        grounded_claims_json=draft.get("grounded_claims_json"),
    )
    return CapabilityResult(
        request_id=uuid4(),
        capability="fitness",
        status="completed",
        summary="Training plan drafted; ready for independent verification.",
        artifacts={"artifact_ready": True},
    )


def _run_verification(state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult:
    """verify_plan and verify_macros are both "check this against the user's goal" requests,
    not mutually exclusive actions -- a submission can carry a structured workout, explicit
    macro numbers, both, or neither, independent of which single intent the LLM classifier
    happened to pick (e.g. a full plan pasted alongside a "Macro Targets" section used to get
    classified verify_macros and silently lose the entire training-plan review). Detect
    whichever of {structured workout, macro numbers} is actually present in the text and
    evaluate all of it in one pass; `ctx.intent` only decides the fallback message for the
    case where neither is found."""
    workspace = state["workspace_path"]
    calories_data = fitness_tools.calculate_calories(workspace)
    if calories_data["macro_targets"] is None:
        return _missing_biometrics_result()

    text = (
        state.get("submitted_plan_text")
        or fitness_tools.load_submitted_plan_text(workspace)
        or state["query"]
    )
    normalized = fitness_tools.normalize_submitted(workspace, text)
    structured_workout = normalized["structured_workout"]
    reported = judge_reported_macros(text).model_dump()
    has_macros = any(value is not None for value in reported.values())

    if structured_workout is None and not has_macros:
        if ctx.intent == "verify_plan":
            # No recognizable workout and no macro numbers in the text at all --
            # `missing_structured_workout` stays an internal diagnostic (see
            # fitness/utils.py); the user gets a qualitative LLM review instead of that
            # raw code as their final response.
            review = fitness_tools.qualitative_review_submitted_plan(text)
            return CapabilityResult(
                request_id=uuid4(),
                capability="fitness",
                status="completed",
                summary=review,
                artifacts={"verification_passed": False},
            )
        result = fitness_tools.evaluate_macros(workspace, reported)
        return CapabilityResult(
            request_id=uuid4(),
            capability="fitness",
            status="completed",
            summary=result["assessment"],
        )

    if structured_workout is None:
        # Macro numbers stated but no workout structure recognized -- a plain macro
        # verdict, same as before.
        result = fitness_tools.evaluate_macros(workspace, reported)
        return CapabilityResult(
            request_id=uuid4(),
            capability="fitness",
            status="completed",
            summary=result["assessment"],
        )

    safety = fitness_tools.validate_plan(workspace, structured_workout)
    passed = safety.get("passed", False)
    # A natural-language explanation (goal fit, volume/exercise-selection adequacy,
    # sets/reps/frequency, weaknesses with concrete fixes, and -- when has_macros -- macro
    # fit too) instead of a bare pass/fail or raw feedback codes -- verification_passed
    # still carries the deterministic verdict for any programmatic gating, this is only the
    # user-facing text.
    response = fitness_tools.explain_verified_plan(
        workspace,
        structured_workout,
        safety,
        reported_macros=reported if has_macros else None,
    )
    return CapabilityResult(
        request_id=uuid4(),
        capability="fitness",
        status="completed",
        summary=response,
        artifacts={"verification_passed": passed},
    )


def _run_read_only(state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult:
    workspace = state["workspace_path"]
    if ctx.intent in ("verify_macros", "verify_plan"):
        return _run_verification(state, ctx)
    if ctx.intent == "calculate_calories":
        result = fitness_tools.calculate_calories(workspace)
        macros = result["macro_targets"]
        if macros is None:
            return _missing_biometrics_result()
        response = (
            f"Estimated TDEE: {macros['tdee']} kcal/day. "
            f"Target calories: {macros['calories']} kcal with {macros['protein_g']}g protein."
        )
        return CapabilityResult(
            request_id=uuid4(),
            capability="fitness",
            status="completed",
            summary=response,
        )
    return CapabilityResult(
        request_id=uuid4(),
        capability="fitness",
        status="completed",
        summary="I can help with training plans, macros, and fitness questions.",
    )


def _after_verification(state: OrchestrationState) -> CapabilityResult:
    last = state.get("last_capability_result") or {}
    if last.get("capability") != "verification":
        return _run_build_plan(state, ExecutionContext.model_validate(state["execution_context"]))
    passed = bool((last.get("artifacts") or {}).get("passed", False))
    # Verification's own result never gates HITL (see persist_trigger_data,
    # core/persist/utils.py): approval_status=="approved" is the only persist
    # gate, so a human must always get the chance to review, approve, reject,
    # or request a revision -- even when verification didn't fully pass.
    return CapabilityResult(
        request_id=uuid4(),
        capability="fitness",
        status="completed",
        summary="Plan verified; ready for approval.",
        artifacts={"artifact_ready": True, "verification_passed": passed},
    )


class SupervisorRoutedFitnessExecutor:
    """Fixed tool sequence per intent -- no LLM reasoning about which tool to call.
    Reports status/blocking_reason/missing_information/summary/artifacts and lets
    the Supervisor + Policy Engine (see `core.orchestration.routing.policy_engine`) route
    from there; never decides what runs next itself."""

    def execute(self, state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult:
        last = state.get("last_capability_result")
        # A pending revision must always rebuild (it changes the plan, so it needs
        # fresh verification too) -- never take the "already verified, just
        # repackage" bounce below, even though `last_capability_result` still shows
        # "verification" from the *original* build until this rebuild produces a
        # fresh result of its own (see core.orchestration.routing.policy_engine's
        # revision_requested rule, which routes here in the first place).
        is_revision = state.get("approval_status") == "revision_requested"
        if (
            last
            and last.get("capability") == "verification"
            and ctx.execution_mode == "artifact"
            and not is_revision
        ):
            return _after_verification(state)
        if is_revision or (ctx.intent == "build_plan" and ctx.execution_mode == "artifact"):
            research = fitness_tools.load_research_result(state["workspace_path"])
            if not research.get("structured_findings"):
                return CapabilityResult(
                    request_id=uuid4(),
                    capability="fitness",
                    status="blocked",
                    blocking_reason="Evidence needed for plan generation",
                    missing_information=["research_findings"],
                )
            return _run_build_plan(state, ctx)
        if ctx.intent == "edit_plan":
            return _run_build_plan(state, ctx)
        return _run_read_only(state, ctx)


_executor: CapabilityExecutor = SupervisorRoutedFitnessExecutor()


def configure_fitness_executor(executor: CapabilityExecutor | None) -> None:
    """Override the Fitness capability executor (used in tests, or to swap in a
    future ReAct agent)."""
    global _executor
    _executor = executor or SupervisorRoutedFitnessExecutor()


def get_fitness_executor() -> CapabilityExecutor:
    return _executor
