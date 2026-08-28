"""The ``verify_faithfulness`` node: score the answer's faithfulness, count the retries, route."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from src.configs.config import settings
from src.enums import FaithfulnessRoute
from src.schemas import GraphState
from src.verification import score_faithfulness


class VerifyFaithfulnessUpdate(TypedDict):
    """The state ``verify_faithfulness`` writes."""

    faithfulness_score: float | None
    qa_retry_count: int
    messages: list[AnyMessage]


def is_faithful(score: float | None) -> bool:
    """Whether a score clears the configured threshold; an unscored answer never does."""

    return score is not None and score >= settings.FAITHFULNESS_THRESHOLD


def _latest_user_text(messages: list[AnyMessage]) -> str:
    """The most recent human turn, which is the question the answer is being scored against."""

    for message in reversed(messages):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return message.content

    return ""


async def verify_faithfulness(state: GraphState) -> VerifyFaithfulnessUpdate:
    """Score the QA answer against the passages it was written from."""

    answer = state.get("qa_answer")
    score = await score_faithfulness(
        question=_latest_user_text(state["messages"]),
        answer=answer,
        passages=state.get("retrieved_context") or [],
    )

    if not is_faithful(score):
        return {
            "faithfulness_score": score,
            "qa_retry_count": state.get("qa_retry_count", 0) + 1,
            "messages": [],
        }

    return {
        "faithfulness_score": score,
        "qa_retry_count": 0,
        "messages": [AIMessage(content=answer)] if answer else [],
    }


def route_after_faithfulness(state: GraphState) -> FaithfulnessRoute:
    """Return a faithful answer, send an unfaithful one back to the agent, or give up."""

    if is_faithful(state.get("faithfulness_score")):
        return FaithfulnessRoute.PASS
    if state.get("qa_retry_count", 0) >= settings.QA_MAX_RETRIES:
        return FaithfulnessRoute.FALLBACK
    return FaithfulnessRoute.RETRY
