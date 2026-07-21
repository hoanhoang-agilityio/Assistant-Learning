from typing import Literal, TypedDict

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


class OrchestrationState(TypedDict):
    """Global orchestration state stored in LangGraph checkpointer."""

    run_id: str
    thread_id: str
    user_id: str
    current_node: str

    query: str
    user_profile: dict
    constraints: dict
    profile_complete: bool
    profile_valid: bool
    days_per_week_explicit: bool

    request_type: RequestType | None
    affected_domains: list[AffectedDomain]

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
    approved_tools: list[str]
    pending_tool: str | None
