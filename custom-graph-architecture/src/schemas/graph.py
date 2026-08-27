"""Graph state for the coaching and QA workflow."""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from langgraph.prebuilt.chat_agent_executor import AgentState

from src.schemas.domain.enums.routes import Intent

HitlDecision = Literal["approve", "reject"]


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


class RetrievedChunk(TypedDict):
    """One passage returned by knowledge retrieval."""

    text: str
    source: str
    score: float


class GraphState(AgentState):
    """State for the whole workflow: guard, intent, coaching branch, HITL and QA branch."""

    # --- Input -------------------------------------------------------------------------
    user_query: str
    user_id: str

    # --- Intent & guard ----------------------------------------------------------------
    intent: NotRequired[Intent | None]
    extracted_facts: NotRequired[dict | None]
    guard_blocked: NotRequired[bool]
    block_reason: NotRequired[str | None]

    # --- User context ------------------------------------------------------------------
    profile: NotRequired[dict | None]
    plan: NotRequired[dict | None]
    context_complete: NotRequired[bool]
    missing_fields: NotRequired[list[str]]
    revision_fields: NotRequired[list[str]]
    user_info_retry_count: NotRequired[int]

    # --- Coaching ----------------------------------------------------------------------
    coach_retry_count: NotRequired[int]
    verification_result: NotRequired[dict | None]

    # --- HITL --------------------------------------------------------------------------
    hitl_decision: NotRequired[HitlDecision | None]
    hitl_feedback: NotRequired[str | None]
    hitl_retry_count: NotRequired[int]

    # --- QA / RAG ----------------------------------------------------------------------
    qa_answer: NotRequired[str | None]
    retrieved_context: NotRequired[list[RetrievedChunk] | None]
    faithfulness_score: NotRequired[float | None]
    qa_retry_count: NotRequired[int]

    # --- Final output ------------------------------------------------------------------
    final_message: NotRequired[str | None]


def initial_state(user_query: str, user_id: str) -> GraphState:
    """Build the starting state for one run, with every key populated."""

    if not user_id:
        raise ValueError("user_id is required to start a run")

    return GraphState(
        messages=[{"role": "user", "content": user_query}],
        user_query=user_query,
        user_id=user_id,
        intent=None,
        extracted_facts=None,
        guard_blocked=False,
        block_reason=None,
        profile=None,
        plan=None,
        context_complete=False,
        missing_fields=[],
        revision_fields=[],
        user_info_retry_count=0,
        coach_retry_count=0,
        verification_result=None,
        hitl_decision=None,
        hitl_feedback=None,
        hitl_retry_count=0,
        qa_answer=None,
        retrieved_context=None,
        faithfulness_score=None,
        qa_retry_count=0,
        final_message=None,
    )
