"""Intent classification for the first post-guard routing step."""

from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.core.configs.config import settings
from src.core.langgraph.prompts import build_intent_classifier_messages
from src.core.logging import logger
from src.schemas import Intent

DEFAULT_INTENT: Intent = "qa"


class IntentDecision(BaseModel):
    """Structured output for the intent classifier."""

    intent: Intent = Field(description="One of: coaching, qa, off_topic.")


@lru_cache
def _build_classifier() -> ChatOpenAI:
    """Build the shared classifier model from application settings."""
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        model=settings.DEFAULT_LLM_MODEL,
        max_tokens=32,
        timeout=settings.LLM_TOTAL_TIMEOUT,
        max_retries=settings.MAX_LLM_CALL_RETRIES,
    )


async def classify_user_intent(user_query: str) -> Intent:
    """Classify the user's request for graph routing."""

    try:
        classifier = _build_classifier().with_structured_output(IntentDecision)
        decision = await classifier.ainvoke(build_intent_classifier_messages(user_query))
    except Exception as error:
        logger.exception(
            "intent_classification_failed",
            error=str(error),
            fallback_intent=DEFAULT_INTENT,
        )
        return DEFAULT_INTENT
    return decision.intent
