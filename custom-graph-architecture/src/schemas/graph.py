"""Graph state for the coaching and QA workflow."""

from typing import Literal, NotRequired, TypedDict

from langgraph.prebuilt.chat_agent_executor import AgentState

Intent = Literal["coaching", "qa", "off_topic"]
HitlDecision = Literal["approve", "reject"]


class RetrievedChunk(TypedDict):
    """One passage returned by knowledge retrieval.

    Attributes:
        text: The passage itself.
        source: Document the passage came from, for citation and for RAGAS scoring.
        score: Cosine similarity against the query embedding.
    """

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
    guard_blocked: NotRequired[bool]
    block_reason: NotRequired[str | None]

    # --- User context ------------------------------------------------------------------
    profile: NotRequired[dict | None]
    plan: NotRequired[dict | None]
    context_complete: NotRequired[bool]
    missing_fields: NotRequired[list[str]]
    user_info_retry_count: NotRequired[int]

    # --- Coaching ----------------------------------------------------------------------
    todo: NotRequired[list[dict] | None]
    coach_retry_count: NotRequired[int]
    verification_result: NotRequired[dict | None]

    # --- HITL --------------------------------------------------------------------------
    hitl_decision: NotRequired[HitlDecision | None]
    hitl_feedback: NotRequired[str | None]
    hitl_retry_count: NotRequired[int]

    # --- QA / RAG ----------------------------------------------------------------------
    qa_answer: NotRequired[str | None]
    retrieved_context: NotRequired[list[RetrievedChunk] | None]
    ragas_score: NotRequired[float | None]
    qa_retry_count: NotRequired[int]

    # --- Final output ------------------------------------------------------------------
    final_message: NotRequired[str | None]


def initial_state(user_query: str, user_id: str) -> GraphState:
    """Build the starting state for one run, with every key populated.

    Args:
        user_query: The user's text for this turn.
        user_id: Owner of the run.

    Returns:
        GraphState: A fully populated state ready to invoke the graph with.

    Raises:
        ValueError: If ``user_id`` is empty — it scopes long-term memory, and an empty one
            would read and write another user's namespace.
    """
    if not user_id:
        raise ValueError("user_id is required to start a run")

    return GraphState(
        messages=[{"role": "user", "content": user_query}],
        user_query=user_query,
        user_id=user_id,
        intent=None,
        guard_blocked=False,
        block_reason=None,
        profile=None,
        plan=None,
        context_complete=False,
        missing_fields=[],
        user_info_retry_count=0,
        todo=None,
        coach_retry_count=0,
        verification_result=None,
        hitl_decision=None,
        hitl_feedback=None,
        hitl_retry_count=0,
        qa_answer=None,
        retrieved_context=None,
        ragas_score=None,
        qa_retry_count=0,
        final_message=None,
    )
