from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.orchestration.state import ApprovalStatus


class CreateRunRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = Field(
        default=None,
        description="Optional user id for rate limiting (X-User-Id header wins).",
    )
    submitted_plan_text: str | None = Field(
        default=None,
        description="An existing plan the user wants checked, not regenerated.",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional client-supplied key. A repeated request with the same key "
            "returns the run already created for it instead of starting a new one."
        ),
    )


class ResumeRunRequest(BaseModel):
    user_response: str | None = Field(
        default=None,
        description="Free-text user response (legacy). Prefer decision_type.",
    )
    approval_status: ApprovalStatus | None = None
    decision_type: Literal["approve", "reject", "revision"] | None = Field(
        default=None,
        description="Structured HITL decision. Use with message for reject/revision.",
    )
    message: str | None = Field(
        default=None,
        description="Required for reject/revision when using decision_type.",
    )
    form_data: dict[str, Any] | None = Field(
        default=None,
        description="Submitted profile form fields, required when hitl_type is 'profile_form'.",
    )
    submitted_plan_text: str | None = Field(
        default=None,
        description=(
            "An existing plan the user wants checked, not regenerated. Optional here so it "
            "can be attached on any resume call (e.g. after completing the profile form) "
            "without requiring it at initial run creation; existing state is left untouched "
            "when omitted."
        ),
    )


class ContinueRunRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000,
        description="Plan change request in an ongoing conversation (replan without re-asking profile).",
    )


class RunSummaryResponse(BaseModel):
    run_id: str
    query: str
    status: Literal["running", "waiting_hitl", "completed", "failed", "refused", "not_found"]
    steps: list[str]
    updated_at: datetime | None = None


class RunStatusResponse(BaseModel):
    run_id: str
    thread_id: str
    status: Literal["running", "waiting_hitl", "completed", "failed", "refused", "not_found"]
    current_node: str
    query: str
    waiting_for_user: bool
    approval_status: ApprovalStatus | None
    verification_passed: bool
    faithfulness_score: float | None
    intent: str | None
    response_mode: str | None
    active_capability: str | None
    final_response: str | None
    final_artifact_path: str | None
    final_plan: str | None
    hitl_type: str | None
    hitl_message: str | None
    refusal_message: str | None
    steps: list[str]
    next_nodes: list[str]
    error_message: str | None = None
    profile_form: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Raw profile-form interrupt payload (profile/missing_fields/feasibility_issues/"
            "validation_errors), present only when hitl_type is 'profile_form'."
        ),
    )
