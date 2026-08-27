"""The ``verify_faithfulness`` node: score the answer's faithfulness, count the retries, route."""

from typing import TypedDict

from src.core.configs.config import settings
from src.core.langgraph.verification import score_faithfulness
from src.enums import FaithfulnessRoute
from src.schemas import GraphState


class VerifyFaithfulnessUpdate(TypedDict):
    """The state ``verify_faithfulness`` writes."""

    faithfulness_score: float | None
    qa_retry_count: int


def is_faithful(score: float | None) -> bool:
    """Whether a score clears the configured threshold; an unscored answer never does."""

    return score is not None and score >= settings.FAITHFULNESS_THRESHOLD


async def verify_faithfulness(state: GraphState) -> VerifyFaithfulnessUpdate:
    """Score the QA answer against the passages it was written from."""

    score = await score_faithfulness(
        question=state["user_query"],
        answer=state.get("qa_answer"),
        passages=state.get("retrieved_context") or [],
    )

    if is_faithful(score):
        return {"faithfulness_score": score, "qa_retry_count": 0}

    return {
        "faithfulness_score": score,
        "qa_retry_count": state.get("qa_retry_count", 0) + 1,
    }


def route_after_faithfulness(state: GraphState) -> FaithfulnessRoute:
    """Return a faithful answer, send an unfaithful one back to the agent, or give up."""

    if is_faithful(state.get("faithfulness_score")):
        return FaithfulnessRoute.PASS
    if state.get("qa_retry_count", 0) >= settings.QA_MAX_RETRIES:
        return FaithfulnessRoute.FALLBACK
    return FaithfulnessRoute.RETRY
