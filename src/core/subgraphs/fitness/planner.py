"""LLM structured workout generation for the Fitness subgraph."""

from collections.abc import Callable
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from core.grounding.schema import GroundedClaim
from core.grounding.validate import allowed_source_urls, filter_grounded_claims
from core.llm.contracts import validate_fitness_planner_payload
from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import set_llm_metrics_node
from core.llm.payload import compact_json, limit_feedback_items
from core.llm.serializers import (
    compact_evidence_for_llm,
    compact_execution_plan_for_llm,
    compact_macro_targets_for_llm,
    compact_profile_for_llm,
    compact_structured_findings,
)
from core.planning.schema import ExecutionPlan
from core.subgraphs.fitness.prompts import (
    FITNESS_PLANNER_SYSTEM_PROMPT,
    build_fitness_edit_system_prompt,
)
from core.subgraphs.fitness.schema import EditOperation, StructuredWorkout
from core.subgraphs.research.schema import ResearchFindings

PlannerOverride = Callable[..., StructuredWorkout]

_AGENT_OVERRIDE: PlannerOverride | None = None


def configure_fitness_planner(override: PlannerOverride | None) -> None:
    """Override the fitness planner (used in tests)."""
    global _AGENT_OVERRIDE
    _AGENT_OVERRIDE = override


def _coerce_structured_findings(
    structured_findings: ResearchFindings | dict[str, Any] | None,
) -> ResearchFindings | None:
    if structured_findings is None:
        return None
    if isinstance(structured_findings, ResearchFindings):
        return structured_findings
    return ResearchFindings.model_validate(structured_findings)


def build_planner_context_payload(
    *,
    profile: dict[str, Any],
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    execution_plan: ExecutionPlan | dict[str, Any] | None,
    structured_findings: ResearchFindings | dict[str, Any] | None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the stable part of the planner payload (identical across retries).

    Kept as its own serialized block so a first-attempt-vs-retry call pair
    shares a byte-identical leading prefix for OpenAI's prompt caching to
    match against (see build_planner_feedback_payload for the part that
    actually changes on retry).

    Deliberately does not carry `previous_workout` -- in edit mode that's
    promoted to its own top-level CURRENT WORKOUT block by
    generate_structured_workout (see below), not buried as one field among
    profile/macros/training_constraints/execution_plan/structured_findings.
    """
    findings = _coerce_structured_findings(structured_findings)
    return {
        "profile": compact_profile_for_llm(profile),
        "macro_targets": compact_macro_targets_for_llm(macro_targets),
        "training_constraints": training_constraints,
        "execution_plan": compact_execution_plan_for_llm(execution_plan),
        "structured_findings": compact_structured_findings(findings),
        "evidence_snippets": compact_evidence_for_llm(evidence or []),
    }


def build_planner_feedback_payload(
    *,
    planner_feedback: list[str],
    verification_feedback: str | None,
    revision_feedback: str | None = None,
) -> dict[str, Any]:
    """Build the variable part of the planner payload (the only part a retry changes)."""
    payload: dict[str, Any] = {
        "planner_feedback": limit_feedback_items(planner_feedback),
        "verification_feedback": verification_feedback,
    }
    stripped_revision = (revision_feedback or "").strip()
    if stripped_revision:
        payload["revision_feedback"] = stripped_revision
    return payload


def build_planner_payload(
    *,
    profile: dict[str, Any],
    constraints: dict[str, Any],
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    execution_plan: ExecutionPlan | dict[str, Any] | None,
    structured_findings: ResearchFindings | dict[str, Any] | None,
    planner_feedback: list[str],
    verification_feedback: str | None,
    revision_feedback: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the full planner payload dict (validation and payload-budget checks)."""
    del constraints
    payload = {
        **build_planner_context_payload(
            profile=profile,
            macro_targets=macro_targets,
            training_constraints=training_constraints,
            execution_plan=execution_plan,
            structured_findings=structured_findings,
            evidence=evidence,
        ),
        **build_planner_feedback_payload(
            planner_feedback=planner_feedback,
            verification_feedback=verification_feedback,
            revision_feedback=revision_feedback,
        ),
    }
    validate_fitness_planner_payload(payload)
    return payload


def sanitize_workout_evidence_applied(
    workout: StructuredWorkout,
    *,
    structured_findings: ResearchFindings | dict[str, Any] | None,
    evidence: list[dict[str, Any]] | None,
) -> StructuredWorkout:
    """Drop evidence_applied claims whose source_url is not in the allowlist."""
    findings = _coerce_structured_findings(structured_findings)
    recommended = list(findings.recommended_sources) if findings else []
    allow = allowed_source_urls(
        evidence=evidence or [],
        recommended_sources=recommended,
    )
    if findings:
        for item in findings.key_findings:
            allow.add(item.source_url)
    filtered = filter_grounded_claims(workout.evidence_applied, allow)
    if [item.model_dump() for item in filtered] == [
        item.model_dump() for item in workout.evidence_applied
    ]:
        return workout
    return workout.model_copy(update={"evidence_applied": filtered})


def generate_structured_workout(
    *,
    profile: dict[str, Any],
    constraints: dict[str, Any],
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    execution_plan: ExecutionPlan | dict[str, Any] | None,
    structured_findings: ResearchFindings | dict[str, Any] | None,
    planner_feedback: list[str],
    verification_feedback: str | None,
    revision_feedback: str | None = None,
    mode: Literal["generate", "edit"] = "generate",
    previous_workout: dict[str, Any] | None = None,
    edit_operation: EditOperation | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> StructuredWorkout:
    """Generate a structured workout via LLM structured output.

    In "edit" mode, the message is restructured around `previous_workout` as
    the primary editing context (CURRENT WORKOUT / USER REQUEST / TASK, with
    everything else demoted to an ADDITIONAL CONTEXT block) and scored against
    a system prompt composed by build_fitness_edit_system_prompt() -- the base
    edit hard-constraints plus operation-specific rules for `edit_operation`,
    when known -- instead of the base generation prompt, so the model is told
    it is editing, not generating a new plan. The output schema and all
    downstream parsing/validation are identical between modes.
    """
    findings = _coerce_structured_findings(structured_findings)
    if _AGENT_OVERRIDE is not None:
        workout = _AGENT_OVERRIDE(
            profile=profile,
            constraints=constraints,
            macro_targets=macro_targets,
            training_constraints=training_constraints,
            execution_plan=execution_plan,
            structured_findings=findings,
            planner_feedback=planner_feedback,
            verification_feedback=verification_feedback,
            evidence=evidence,
        )
        return sanitize_workout_evidence_applied(
            workout, structured_findings=findings, evidence=evidence
        )
    del constraints
    context_payload = build_planner_context_payload(
        profile=profile,
        macro_targets=macro_targets,
        training_constraints=training_constraints,
        execution_plan=execution_plan,
        structured_findings=findings,
        evidence=evidence,
    )
    feedback_payload = build_planner_feedback_payload(
        planner_feedback=planner_feedback,
        verification_feedback=verification_feedback,
        revision_feedback=revision_feedback,
    )
    validate_fitness_planner_payload({**context_payload, **feedback_payload})

    if mode == "edit" and previous_workout is not None:
        message_content = (
            "CURRENT WORKOUT (this is the plan you are editing -- the immutable baseline):\n"
            + compact_json(previous_workout)
            + "\n\nUSER REQUEST:\n"
            + (revision_feedback or "").strip()
            + "\n\nTASK:\nYou are EDITING the CURRENT WORKOUT above, not generating a new "
            "plan. Apply only the change described in USER REQUEST. Every part of CURRENT "
            "WORKOUT not implicated by USER REQUEST must be reproduced exactly as given.\n\n"
            "ADDITIONAL CONTEXT:\n"
            + compact_json(context_payload)
            + "\n"
            + compact_json(feedback_payload)
        )
    else:
        # Two separate compact_json blocks, not one merged dict: this keeps the
        # context block's serialized bytes identical between a first attempt and
        # a safety-check retry (only feedback_payload differs), giving OpenAI's
        # prompt caching a real repeated prefix to match against on retry.
        message_content = compact_json(context_payload) + "\n" + compact_json(feedback_payload)
    if mode == "edit":
        operation_name = edit_operation.operation if edit_operation is not None else None
        system_prompt = build_fitness_edit_system_prompt(operation_name)
        prompt_cache_key = (
            f"fitness_planner_edit_{operation_name}" if operation_name else "fitness_planner_edit"
        )
    else:
        system_prompt = FITNESS_PLANNER_SYSTEM_PROMPT
        prompt_cache_key = "fitness_planner"
    token = set_llm_metrics_node("fitness_planner")
    try:
        workout = invoke_standard_structured_output(
            StructuredWorkout,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=message_content),
            ],
            prompt_cache_key=prompt_cache_key,
        )
    finally:
        from core.llm.metrics import reset_llm_metrics_node

        reset_llm_metrics_node(token)
    return sanitize_workout_evidence_applied(
        workout, structured_findings=findings, evidence=evidence
    )


def resolve_grounded_claims_for_render(
    *,
    structured_workout: dict[str, Any] | StructuredWorkout,
    structured_findings: ResearchFindings | dict[str, Any] | None,
    evidence: list[dict[str, Any]] | None,
) -> list[GroundedClaim]:
    """Prefer validated evidence_applied; fall back to research key_findings."""
    workout = (
        structured_workout
        if isinstance(structured_workout, StructuredWorkout)
        else StructuredWorkout.model_validate(structured_workout)
    )
    findings = _coerce_structured_findings(structured_findings)
    recommended = list(findings.recommended_sources) if findings else []
    allow = allowed_source_urls(evidence=evidence or [], recommended_sources=recommended)
    if findings:
        for item in findings.key_findings:
            allow.add(item.source_url)
    applied = filter_grounded_claims(workout.evidence_applied, allow)
    if applied:
        return applied
    if findings:
        return filter_grounded_claims(findings.key_findings, allow)
    return []
