"""LLM factory for standard-tier and XHIGH-tier structured extraction."""

import logging
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from core.config.settings import get_settings

logger = logging.getLogger(__name__)


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


@lru_cache
def get_xhigh_openai_llm() -> BaseChatModel:
    """Return the configured OpenAI model for XHIGH-tier structured output."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for XHIGH-tier LLM calls")
    return ChatOpenAI(
        model=settings.openai_xhigh_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


@lru_cache
def get_xhigh_anthropic_llm() -> BaseChatModel:
    """Return the configured Anthropic fallback model for XHIGH-tier structured output."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for XHIGH-tier Anthropic fallback")
    return ChatAnthropic(
        model=settings.anthropic_xhigh_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )


def get_xhigh_llm() -> BaseChatModel:
    """Return the primary XHIGH-tier chat model (OpenAI)."""
    return get_xhigh_openai_llm()


def invoke_xhigh_structured_output[T: BaseModel](
    output_schema: type[T],
    messages: list[BaseMessage],
) -> T:
    """Invoke structured output using OpenAI, falling back to Anthropic on failure."""
    settings = get_settings()
    openai_error: Exception | None = None

    if settings.openai_api_key:
        try:
            structured_llm = get_xhigh_openai_llm().with_structured_output(output_schema)
            return structured_llm.invoke(messages)
        except Exception as exc:
            openai_error = exc
            logger.warning(
                "XHIGH OpenAI structured output failed; trying Anthropic fallback: %s",
                exc,
            )

    if settings.anthropic_api_key:
        try:
            structured_llm = get_xhigh_anthropic_llm().with_structured_output(output_schema)
            return structured_llm.invoke(messages)
        except Exception as anthropic_error:
            if openai_error is not None:
                raise RuntimeError(
                    "XHIGH structured output failed for both OpenAI and Anthropic"
                ) from anthropic_error
            raise

    if openai_error is not None:
        raise openai_error

    raise RuntimeError(
        "OPENAI_API_KEY or ANTHROPIC_API_KEY is required for XHIGH-tier structured output"
    )
