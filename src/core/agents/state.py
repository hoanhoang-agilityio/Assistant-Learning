from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from core.agents.execution_context import Intent
from core.agents.topic_scope_judge import ScopeDecision, ScopeRequest

ApprovalStatus = Literal["pending", "approved", "rejected", "revision_requested"]


class ScopeResult(BaseModel):
    """Orchestration-level record of the scope guardrail's verdict for this run."""

    decision: ScopeDecision
    supported_requests: list[ScopeRequest]
    unsupported_requests: list[ScopeRequest]
    reason: str = Field(description="One concise sentence explaining the decision.")


class OrchestrationState(TypedDict):
    """Global orchestration state stored in LangGraph checkpointer."""

    run_id: str
    thread_id: str
    user_id: str
    current_node: str

    query: str
    fitness_query: str | None

    scope_result: dict | None
    execution_context: dict | None
    intent: Intent | None

    profile_complete: bool
    profile_valid: bool
    days_per_week_explicit: bool

    submitted_plan_text: str | None

    active_capability: str | None
    capability_results: dict[str, dict]
    last_capability_result: dict | None

    verification_passed: bool
    faithfulness_score: float | None
    # L1 Phase 4: which capability owns fixing the last verification failure
    # ("research" | "fitness" | None), the report's feedback text, and how many
    # times the Policy Engine has already auto-retried because of it. Set by
    # verification/capability.py from the executor's report; consumed by
    # policy_engine.enforce_routing_invariants to decide whether to route back
    # automatically instead of straight to HITL.
    verification_retry_target: str | None
    verification_feedback: str | None
    verification_retry_count: int

    hop_count: int
    agent_trail: list[str]
    next_agent: str | None

    waiting_for_user: bool
    approval_status: ApprovalStatus | None
    user_response: str | None
    revision_feedback: str | None
    revision_count: int

    workspace_path: str
    final_artifact_path: str | None
    final_response: str | None
    refusal_message: str | None
    run_complete: bool

    steps: list[str]
