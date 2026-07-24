from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from core.agents.topic_scope_judge import ScopeDecision, ScopeRequest

RouteDecision = Literal["FIX_REASONING", "REPLAN", "RERESEARCH", "HITL", "COMPLETE", "REFUSED"]
RequestType = Literal[
    "training_plan",
    "macro_calculation",
    "fat_loss",
    "muscle_gain",
    "strength",
    "endurance",
    "general_fitness",
]
AffectedDomain = Literal["planning", "research", "fitness", "verify"]
ApprovalStatus = Literal["pending", "approved", "rejected", "revision_requested"]


class ScopeResult(BaseModel):
    """Orchestration-level record of the scope guardrail's verdict for this run.

    Deliberately a separate type from `TopicScopeJudgement` (the LLM judge's own output
    contract in topic_scope_judge.py): this is what gets persisted in checkpointed state
    and exposed to logging/analytics, so it must stay stable even if the judge's prompt
    or schema changes. `check_topic_scope` (core/agents/tools.py) is the translation
    boundary between the two -- it partitions the judge's `requests` into
    supported/unsupported here. Keeping full ScopeRequest objects (not just text) retains
    action_type for future analytics/guardrails without revisiting this layer.
    """

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
    profile_complete: bool
    profile_valid: bool
    days_per_week_explicit: bool

    request_type: RequestType | None
    affected_domains: list[AffectedDomain]
    execution_plan: dict | None
    submitted_plan_text: str | None

    route_decision: RouteDecision | None
    retry_count: int
    replan_count: int

    verification_passed: bool
    faithfulness_score: float | None

    waiting_for_user: bool
    approval_status: ApprovalStatus | None
    user_response: str | None
    revision_feedback: str | None

    workspace_path: str
    final_artifact_path: str | None
    refusal_message: str | None

    steps: list[str]
