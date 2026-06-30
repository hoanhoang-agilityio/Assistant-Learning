from typing import Any, Literal

from pydantic import BaseModel, Field

from core.agents.state import ApprovalStatus


class CreateRunRequest(BaseModel):
    query: str = Field(min_length=3)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ResumeRunRequest(BaseModel):
    user_response: str = Field(min_length=1)
    approval_status: ApprovalStatus | None = None


class RunStatusResponse(BaseModel):
    run_id: str
    thread_id: str
    status: Literal["running", "waiting_hitl", "completed", "failed", "not_found"]
    current_node: str
    query: str
    waiting_for_user: bool
    approval_status: ApprovalStatus | None
    verification_passed: bool
    faithfulness_score: float | None
    route_decision: str | None
    request_type: str | None
    final_artifact_path: str | None
    final_plan: str | None
    hitl_type: str | None
    hitl_message: str | None
    next_nodes: list[str]
    error_message: str | None = None
