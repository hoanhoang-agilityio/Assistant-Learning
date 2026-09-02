"""Graph state for the supervisor-orchestrated coaching and QA workflow."""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from langgraph.prebuilt.chat_agent_executor import AgentState

ApprovalDecision = Literal["approve", "reject"]
ApprovalSource = Literal["coach_agent"]
ApprovalKind = Literal["plan"]
CoachOutcome = Literal["answered", "drafted"]
NextAgent = Literal["user_agent", "coach_agent", "qa_agent", "FINISH"]
ProfileRequiredFor = Literal["plan"]
ProfileStatus = Literal["ready", "need_input"]


@dataclass(frozen=True, slots=True)
class CoachContext:
    """What the coach agent's tools read for themselves rather than being told."""

    user_id: str
    profile: dict | None = None


@dataclass(frozen=True, slots=True)
class QaContext:
    """What the QA agent's tools read for themselves rather than being told."""

    user_id: str
    profile: dict | None = None


@dataclass(frozen=True, slots=True)
class UserAgentContext:
    """What the user agent's tools read for themselves rather than being told."""

    user_id: str
    profile: dict | None = None


class RetrievedChunk(TypedDict):
    """One passage returned by knowledge retrieval."""

    text: str
    source: str
    score: float


class PendingApproval(TypedDict):
    """What ``plan_approval`` shows the reviewer."""

    source: ApprovalSource
    kind: ApprovalKind
    summary: str
    payload: dict


class VerificationCycleReset(TypedDict):
    """The verification fields a finished plan attempt hands back cleared."""

    verification_result: None
    coach_retry_count: int


def cleared_verification() -> VerificationCycleReset:
    """The reset the end of a failed plan attempt writes.

    Left standing, the last attempt's errors reach the coach as `<verification_errors>` on
    every later turn of the same thread — including one that only asks what the stored plan
    holds, which the coach would then answer with a plan revision — and the spent retry
    budget sends the next attempt's first failure straight to `notify_fail`.
    """

    return {"verification_result": None, "coach_retry_count": 0}


class ApprovalCycleReset(TypedDict):
    """The approval fields a finished review cycle hands back cleared."""

    pending_approval: None
    approval_decision: None
    approval_feedback: None
    approval_retry_count: int


def cleared_approval() -> ApprovalCycleReset:
    """The reset every terminal outcome of a review writes.

    State is checkpointed per conversation, so a decision left standing outlives the plan
    it was about: the next plan the same thread asks for would be built against the last
    one's rejection, as ``<reviewer_feedback>`` and as a retry budget already part spent.
    Only the outcomes that end a cycle clear it — a revise hands the feedback to the coach
    precisely so it can act on it.
    """

    return {
        "pending_approval": None,
        "approval_decision": None,
        "approval_feedback": None,
        "approval_retry_count": 0,
    }


class GraphState(AgentState):
    """State for the whole workflow: supervisor routing, coaching branch, QA branch, shared approval."""

    # --- Input ---------------------------------------------------------------------
    user_id: str

    # --- Guard -----------------------------------------------------------------------
    block_reason: NotRequired[str | None]

    # --- Supervisor loop ---------------------------------------------------------------
    next: NotRequired[NextAgent | None]
    iteration_count: NotRequired[int]
    summary: NotRequired[str]

    # --- User context ------------------------------------------------------------------
    profile: NotRequired[dict | None]
    profile_draft: NotRequired[dict | None]
    plan: NotRequired[dict | None]
    profile_required_for: NotRequired[ProfileRequiredFor | None]
    profile_status: NotRequired[ProfileStatus | None]

    # --- Coaching ----------------------------------------------------------------------
    coach_outcome: NotRequired[CoachOutcome | None]
    coach_retry_count: NotRequired[int]
    verification_result: NotRequired[dict | None]

    # --- Shared approval: the coach's plan -----------------------------------------------
    pending_approval: NotRequired[PendingApproval | None]
    approval_decision: NotRequired[ApprovalDecision | None]
    approval_feedback: NotRequired[str | None]
    approval_retry_count: NotRequired[int]

    # --- QA / RAG ----------------------------------------------------------------------
    qa_answer: NotRequired[str | None]
    retrieved_context: NotRequired[list[RetrievedChunk] | None]
    faithfulness_score: NotRequired[float | None]
    qa_retry_count: NotRequired[int]


def initial_state(user_query: str, user_id: str) -> GraphState:
    """Build the starting state for one run, with every key populated."""

    if not user_id:
        raise ValueError("user_id is required to start a run")

    return GraphState(
        messages=[{"role": "user", "content": user_query}],
        user_id=user_id,
        block_reason=None,
        next=None,
        iteration_count=0,
        summary="",
        profile=None,
        profile_draft=None,
        plan=None,
        profile_required_for=None,
        profile_status=None,
        coach_outcome=None,
        coach_retry_count=0,
        verification_result=None,
        pending_approval=None,
        approval_decision=None,
        approval_feedback=None,
        approval_retry_count=0,
        qa_answer=None,
        retrieved_context=None,
        faithfulness_score=None,
        qa_retry_count=0,
    )


def is_blocked(state: GraphState) -> bool:
    """Whether the guard rejected this turn, read off the reason rather than a flag."""
    return state.get("block_reason") is not None
