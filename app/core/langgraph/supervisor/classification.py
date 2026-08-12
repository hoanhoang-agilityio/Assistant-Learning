"""Intent classification used by the supervisor topic gate."""

from langchain_core.messages import HumanMessage

from app.core.langgraph.supervisor.prompts import load_classify_prompt
from app.schemas.graph import IntentDecision
from app.services.llm.service import llm_service

CONTEXT_TURNS = 6
_CLASSIFIER_MODEL = "gpt-5-mini"


async def llm_classify(conversation: str) -> IntentDecision:
    """Call the classifier model and return its validated decision."""
    return await llm_service.call(
        [HumanMessage(content=load_classify_prompt(conversation))],
        model_name=_CLASSIFIER_MODEL,
        response_format=IntentDecision,
    )


__all__ = ["CONTEXT_TURNS", "llm_classify"]
