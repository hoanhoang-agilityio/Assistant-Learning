"""The ``ragas_verification`` node: score the answer's faithfulness, count the retries, route."""

from typing import Literal, TypedDict

from src.core.configs.config import settings
from src.core.langgraph.verification import score_faithfulness
from src.schemas import GraphState

RagasRoute = Literal["pass", "retry", "fallback"]


class RagasVerificationUpdate(TypedDict):
    """The state ``ragas_verification`` writes."""

    ragas_score: float | None
    qa_retry_count: int


def is_faithful(score: float | None) -> bool:
    """Whether a score clears the configured threshold; an unscored answer never does."""

    return score is not None and score >= settings.RAGAS_FAITHFULNESS_THRESHOLD


async def ragas_verification(state: GraphState) -> RagasVerificationUpdate:
    """Score the QA answer against the passages it was written from."""

    score = await score_faithfulness(
        question=state["user_query"],
        answer=state.get("qa_answer"),
        passages=state.get("retrieved_context") or [],
    )

    if is_faithful(score):
        return {"ragas_score": score, "qa_retry_count": 0}

    return {"ragas_score": score, "qa_retry_count": state.get("qa_retry_count", 0) + 1}


def route_after_ragas(state: GraphState) -> RagasRoute:
    """Return a faithful answer, send an unfaithful one back to the agent, or give up."""

    if is_faithful(state.get("ragas_score")):
        return "pass"
    if state.get("qa_retry_count", 0) >= settings.QA_MAX_RETRIES:
        return "fallback"
    return "retry"
