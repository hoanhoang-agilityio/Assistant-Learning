"""LLM factory for standard-tier structured extraction."""

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from core.config.settings import get_settings


@lru_cache
def get_standard_llm() -> BaseChatModel:
    """Return the configured standard-tier chat model for structured extraction."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM profile extraction")
    return ChatOpenAI(
        model=settings.openai_standard_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
