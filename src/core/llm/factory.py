"""LLM factory for standard-tier and XHIGH-tier structured extraction."""

import logging
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from core.config.settings import get_settings
from core.rate_limit import AIRateLimiter
from core.rate_limit.limiter import estimate_message_tokens

logger = logging.getLogger(__name__)

_rate_limiter = AIRateLimiter()


def get_rate_limiter() -> AIRateLimiter:
    return _rate_limiter


def configure_rate_limiter(limiter: AIRateLimiter | None) -> None:
    """Override the shared rate limiter (used in tests)."""
    global _rate_limiter
    _rate_limiter = limiter or AIRateLimiter()


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


def invoke_bound_llm(llm: BaseChatModel, messages: list[BaseMessage], *, model_name: str) -> Any:
    """Invoke a tool-bound chat model with per-user rate limiting."""
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    response = llm.invoke(messages)
    _rate_limiter.record_active_user_response(
        response,
        model_name=model_name,
        estimated_input_tokens=estimated_tokens,
    )
    return response


def invoke_standard_llm(messages: list[BaseMessage]) -> Any:
    """Invoke the standard-tier model with per-user rate limiting."""
    settings = get_settings()
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    response = get_standard_llm().invoke(messages)
    _rate_limiter.record_active_user_response(
        response,
        model_name=settings.openai_standard_model,
        estimated_input_tokens=estimated_tokens,
    )
    return response


def invoke_standard_structured_output[T: BaseModel](
    output_schema: type[T],
    messages: list[BaseMessage],
) -> T:
    """Invoke structured output using the standard-tier OpenAI model."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for STANDARD-tier structured output")
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    structured_llm = get_standard_llm().with_structured_output(output_schema)
    result = structured_llm.invoke(messages)
    _rate_limiter.record_active_user_response(
        result,
        model_name=settings.openai_standard_model,
        estimated_input_tokens=estimated_tokens,
    )
    return result


def invoke_xhigh_structured_output[T: BaseModel](
    output_schema: type[T],
    messages: list[BaseMessage],
) -> T:
    """Invoke structured output using OpenAI, falling back to Anthropic on failure."""
    settings = get_settings()
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    openai_error: Exception | None = None

    if settings.openai_api_key:
        try:
            structured_llm = get_xhigh_openai_llm().with_structured_output(output_schema)
            result = structured_llm.invoke(messages)
            _rate_limiter.record_active_user_response(
                result,
                model_name=settings.openai_xhigh_model,
                estimated_input_tokens=estimated_tokens,
            )
            return result
        except Exception as exc:
            openai_error = exc
            logger.warning(
                "XHIGH OpenAI structured output failed; trying Anthropic fallback: %s",
                exc,
            )

    if settings.anthropic_api_key:
        try:
            structured_llm = get_xhigh_anthropic_llm().with_structured_output(output_schema)
            result = structured_llm.invoke(messages)
            _rate_limiter.record_active_user_response(
                result,
                model_name=settings.anthropic_xhigh_model,
                estimated_input_tokens=estimated_tokens,
            )
            return result
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
