"""Graph state for the supervisor-orchestrated coaching and QA workflow."""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from langgraph.prebuilt.chat_agent_executor import AgentState

ApprovalDecision = Literal["approve", "reject"]
ApprovalSource = Literal["coach_agent", "user_agent"]
ApprovalKind = Literal["plan", "profile_update"]
NextAgent = Literal["user_agent", "coach_agent", "qa_agent", "FINISH"]


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


class RetrievedChunk(TypedDict):
    """One passage returned by knowledge retrieval."""

    text: str
    source: str
    score: float


class PendingApproval(TypedDict):
    """What ``hitl_agent`` shows, and which caller the decision goes back to."""

    source: ApprovalSource
    kind: ApprovalKind
    summary: str
    payload: dict


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
    plan: NotRequired[dict | None]

    # --- Coaching ----------------------------------------------------------------------
    coach_retry_count: NotRequired[int]
    verification_result: NotRequired[dict | None]

    # --- Shared approval: coach's plan, or user_agent's profile overwrite ---------------
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
        plan=None,
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
