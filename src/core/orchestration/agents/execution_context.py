"""Immutable execution semantics and mutable capability handoff contracts."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "build_plan",
    "edit_plan",
    "verify_plan",
    "verify_macros",
    "research_question",
    "fitness_question",
    "calculate_calories",
]
ExecutionMode = Literal["artifact", "read_only"]
ResponseMode = Literal["answer", "plan", "edit", "verify"]
CapabilityName = Literal[
    "user",
    "planning",
    "research",
    "fitness",
    "verification",
    "hitl",
    "persist",
]
EntryNode = Literal["planning", "research", "fitness"]
ArtifactKind = Literal["training_plan", "submitted_plan", "macro_targets"]
CapabilityStatus = Literal["completed", "partial", "needs_capability", "failed", "blocked"]
JsonValue = str | int | float | bool | None | dict[str, Any] | list[Any]


class ArtifactReference(BaseModel):
    """Immutable reference to an artifact present at request start."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ArtifactKind
    path: str


class ExecutionContext(BaseModel):
    """Frozen semantic contract for a run — no runtime progress or sequencing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: Intent
    execution_mode: ExecutionMode
    response_mode: ResponseMode
    entry_node: EntryNode
    requires_profile: bool
    requires_existing_plan: bool
    current_artifact: ArtifactReference | None
    requested_artifact: ArtifactKind | None


class CapabilityRequest(BaseModel):
    """Typed request to invoke another capability."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID = Field(default_factory=uuid4)
    capability: CapabilityName
    reason: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    return_to: CapabilityName | None = None


class CapabilityResult(BaseModel):
    """Typed result from a capability invocation.

    Evolving towards the AgentResult shape the hybrid Supervisor design consumes
    (`blocking_reason`/`missing_information`/`summary`/`artifacts`/`metadata`, see
    docs/reports plan) -- added here as optional fields so existing callers that only
    set `output`/`next_request` are unaffected until each capability executor is
    migrated. `next_request` and `status in {"needs_capability", "partial"}` are
    retired once the Supervisor (not the capability itself) owns routing; until then
    both shapes coexist.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    capability: CapabilityName
    status: CapabilityStatus
    output: dict[str, JsonValue] = Field(default_factory=dict)
    next_request: CapabilityRequest | None = None

    # AgentResult fields (Supervisor-routed path).
    blocking_reason: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    summary: str = ""
    artifacts: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


def build_execution_context(
    *,
    intent: Intent,
    touches_goal_or_constraints: bool = False,
    has_submitted_plan: bool = False,
    has_existing_plan: bool = False,
) -> ExecutionContext:
    """Deterministically map classified intent to frozen execution semantics."""
    if intent == "build_plan":
        return ExecutionContext(
            intent=intent,
            execution_mode="artifact",
            response_mode="plan",
            entry_node="planning",
            requires_profile=True,
            requires_existing_plan=False,
            current_artifact=None,
            requested_artifact="training_plan",
        )
    if intent == "edit_plan":
        return ExecutionContext(
            intent=intent,
            execution_mode="artifact",
            response_mode="edit",
            entry_node="planning" if touches_goal_or_constraints else "fitness",
            requires_profile=True,
            requires_existing_plan=True,
            current_artifact=ArtifactReference(kind="training_plan", path="fitness/workout.json")
            if has_existing_plan
            else None,
            requested_artifact="training_plan",
        )
    if intent == "verify_plan":
        return ExecutionContext(
            intent=intent,
            execution_mode="read_only",
            response_mode="verify",
            entry_node="fitness",
            # True (unlike verify_macros' sibling read-only intents being False) so the
            # macro-safety check in validate_workout_safety_data has real weight/height/age
            # to check against -- routes through the "user" capability gate first (see
            # route_initial_from_supervisor), which pauses for the profile form only if
            # fields are actually missing/incomplete, then returns here automatically.
            requires_profile=True,
            requires_existing_plan=False,
            current_artifact=ArtifactReference(kind="submitted_plan", path="plan/submitted_plan.md")
            if has_submitted_plan
            else None,
            requested_artifact=None,
        )
    if intent == "verify_macros":
        return ExecutionContext(
            intent=intent,
            execution_mode="read_only",
            response_mode="verify",
            entry_node="fitness",
            requires_profile=True,
            requires_existing_plan=False,
            current_artifact=None,
            requested_artifact=None,
        )
    if intent == "research_question":
        return ExecutionContext(
            intent=intent,
            execution_mode="read_only",
            response_mode="answer",
            entry_node="research",
            requires_profile=False,
            requires_existing_plan=False,
            current_artifact=None,
            requested_artifact=None,
        )
    if intent in ("fitness_question", "calculate_calories"):
        return ExecutionContext(
            intent=intent,
            execution_mode="read_only",
            response_mode="answer",
            entry_node="fitness",
            requires_profile=intent == "calculate_calories",
            requires_existing_plan=False,
            current_artifact=None,
            requested_artifact=None,
        )
    raise ValueError(f"Unsupported intent: {intent}")


def parse_execution_context(data: dict[str, Any] | None) -> ExecutionContext | None:
    if not data:
        return None
    return ExecutionContext.model_validate(data)
