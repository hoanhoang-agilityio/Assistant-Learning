"""LLM factory for standard-tier and XHIGH-tier structured extraction."""

import logging
import time
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from core.config.settings import get_settings
from core.llm.metrics import record_llm_call_metric
from core.rate_limit import AIRateLimiter
from core.rate_limit.limiter import estimate_message_tokens

logger = logging.getLogger(__name__)

_rate_limiter = AIRateLimiter()

_TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "rate limit",
    "rate_limit",
    "429",
    "503",
    "502",
    "500",
    "overloaded",
    "unavailable",
    "connection error",
    "connection reset",
)

_NON_TRANSIENT_ERROR_MARKERS = (
    "validation",
    "json",
    "schema",
    "bad request",
    "invalid",
    "400",
    "401",
    "403",
    "404",
    "length limit",
    "could not parse response",
)


def get_rate_limiter() -> AIRateLimiter:
    return _rate_limiter


def configure_rate_limiter(limiter: AIRateLimiter | None) -> None:
    """Override the shared rate limiter (used in tests)."""
    global _rate_limiter
    _rate_limiter = limiter or AIRateLimiter()


def _is_transient_llm_error(exc: Exception) -> bool:
    """Return True only for errors where a cross-provider retry is worthwhile."""
    message = str(exc).lower()
    if any(marker in message for marker in _NON_TRANSIENT_ERROR_MARKERS):
        return False
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def _structured_output_runnable(
    llm: BaseChatModel,
    output_schema: type[BaseModel],
    *,
    prompt_cache_key: str | None = None,
    method: str = "json_schema",
) -> Any:
    """Bind a safe output token cap and structured-output method.

    method="json_schema" is the OpenAI path's default (also LangChain's own
    current default) — verified live against this repo's actual schemas
    (including StructuredWorkout, the most deeply nested one) before
    switching from the older function_calling method. It shapes the response
    directly rather than through a synthetic tool call, avoiding that
    method's fixed tool-use system-prompt overhead. The Anthropic fallback
    path passes method="function_calling" explicitly (its own safe default)
    since json_schema support there hasn't been live-verified in this repo.

    prompt_cache_key groups repeated calls from the same node under one
    OpenAI cache-routing bucket (per-node, not per-run) so nodes with the
    same static prefix get consistently routed to the same backend cache;
    unused by the Anthropic path.
    """
    settings = get_settings()
    bind_kwargs: dict[str, Any] = {"max_tokens": settings.llm_structured_output_max_tokens}
    if prompt_cache_key:
        bind_kwargs["prompt_cache_key"] = prompt_cache_key
    return llm.bind(**bind_kwargs).with_structured_output(
        output_schema,
        method=method,
    )


def _maybe_record_metric(
    *,
    messages: list[BaseMessage],
    response: Any,
    model_name: str,
    estimated_input_tokens: int,
    latency_ms: float,
) -> None:
    metric = record_llm_call_metric(
        messages=messages,
        response=response,
        model_name=model_name,
        estimated_input_tokens=estimated_input_tokens,
        latency_ms=latency_ms,
    )
    settings = get_settings()
    if not settings.llm_payload_debug:
        return
    logger.debug(
        "LLM payload metric node=%s model=%s in=%s out=%s est_in=%s latency_ms=%.1f keys=%s",
        metric.node,
        metric.model,
        metric.input_tokens,
        metric.output_tokens,
        metric.estimated_input_tokens,
        metric.latency_ms,
        metric.largest_payload_keys,
    )


def _temperature_kwargs(reasoning_effort: str | None) -> dict[str, Any]:
    """Only send temperature when reasoning is off.

    OpenAI's GPT-5 reasoning family does not reliably honor a custom
    `temperature` alongside active reasoning (reasoning_effort not in
    (None, "none")) — some client/library combinations drop or reject it.
    temperature=0 is only safe to send when reasoning is disabled.
    """
    if reasoning_effort in (None, "none"):
        return {"temperature": 0}
    return {}


@lru_cache
def get_standard_llm() -> BaseChatModel:
    """Return the configured standard-tier chat model for structured extraction."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM profile extraction")
    return ChatOpenAI(
        model=settings.openai_standard_model,
        api_key=settings.openai_api_key,
        max_tokens=settings.openai_max_tokens,
        reasoning_effort=settings.openai_standard_reasoning_effort,
        verbosity=settings.openai_verbosity,
        **_temperature_kwargs(settings.openai_standard_reasoning_effort),
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
        max_tokens=settings.openai_max_tokens,
        reasoning_effort=settings.openai_xhigh_reasoning_effort,
        verbosity=settings.openai_verbosity,
        **_temperature_kwargs(settings.openai_xhigh_reasoning_effort),
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
        max_tokens=settings.anthropic_max_tokens,
    )


def get_xhigh_llm() -> BaseChatModel:
    """Return the primary XHIGH-tier chat model (OpenAI)."""
    return get_xhigh_openai_llm()


def invoke_bound_llm(llm: BaseChatModel, messages: list[BaseMessage], *, model_name: str) -> Any:
    """Invoke a tool-bound chat model with per-user rate limiting."""
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    started = time.perf_counter()
    response = llm.invoke(messages)
    latency_ms = (time.perf_counter() - started) * 1000
    _rate_limiter.record_active_user_response(
        response,
        model_name=model_name,
        estimated_input_tokens=estimated_tokens,
    )
    _maybe_record_metric(
        messages=messages,
        response=response,
        model_name=model_name,
        estimated_input_tokens=estimated_tokens,
        latency_ms=latency_ms,
    )
    return response


def invoke_standard_llm(messages: list[BaseMessage]) -> Any:
    """Invoke the standard-tier model with per-user rate limiting."""
    settings = get_settings()
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    started = time.perf_counter()
    response = get_standard_llm().invoke(messages)
    latency_ms = (time.perf_counter() - started) * 1000
    _rate_limiter.record_active_user_response(
        response,
        model_name=settings.openai_standard_model,
        estimated_input_tokens=estimated_tokens,
    )
    _maybe_record_metric(
        messages=messages,
        response=response,
        model_name=settings.openai_standard_model,
        estimated_input_tokens=estimated_tokens,
        latency_ms=latency_ms,
    )
    return response


def invoke_standard_structured_output[T: BaseModel](
    output_schema: type[T],
    messages: list[BaseMessage],
    *,
    prompt_cache_key: str | None = None,
) -> T:
    """Invoke structured output using the standard-tier OpenAI model."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for STANDARD-tier structured output")
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    structured_llm = _structured_output_runnable(
        get_standard_llm(), output_schema, prompt_cache_key=prompt_cache_key
    )
    started = time.perf_counter()
    result = structured_llm.invoke(messages)
    latency_ms = (time.perf_counter() - started) * 1000
    _rate_limiter.record_active_user_response(
        result,
        model_name=settings.openai_standard_model,
        estimated_input_tokens=estimated_tokens,
    )
    _maybe_record_metric(
        messages=messages,
        response=result,
        model_name=settings.openai_standard_model,
        estimated_input_tokens=estimated_tokens,
        latency_ms=latency_ms,
    )
    return result


def invoke_xhigh_structured_output[T: BaseModel](
    output_schema: type[T],
    messages: list[BaseMessage],
    *,
    prompt_cache_key: str | None = None,
) -> T:
    """Invoke structured output using OpenAI, falling back to Anthropic on transient failure."""
    settings = get_settings()
    estimated_tokens = estimate_message_tokens(messages)
    _rate_limiter.check_active_user_tokens(estimated_tokens=estimated_tokens)
    openai_error: Exception | None = None

    if settings.openai_api_key:
        try:
            structured_llm = _structured_output_runnable(
                get_xhigh_openai_llm(), output_schema, prompt_cache_key=prompt_cache_key
            )
            started = time.perf_counter()
            result = structured_llm.invoke(messages)
            latency_ms = (time.perf_counter() - started) * 1000
            _rate_limiter.record_active_user_response(
                result,
                model_name=settings.openai_xhigh_model,
                estimated_input_tokens=estimated_tokens,
            )
            _maybe_record_metric(
                messages=messages,
                response=result,
                model_name=settings.openai_xhigh_model,
                estimated_input_tokens=estimated_tokens,
                latency_ms=latency_ms,
            )
            return result
        except Exception as exc:
            openai_error = exc
            if not _is_transient_llm_error(exc):
                logger.warning(
                    "XHIGH OpenAI structured output failed with non-transient error; skipping fallback: %s",
                    exc,
                )
                raise
            logger.warning(
                "XHIGH OpenAI structured output failed with transient error; trying Anthropic fallback: %s",
                exc,
            )

    if settings.anthropic_api_key and openai_error is not None:
        try:
            structured_llm = _structured_output_runnable(
                get_xhigh_anthropic_llm(), output_schema, method="function_calling"
            )
            started = time.perf_counter()
            result = structured_llm.invoke(messages)
            latency_ms = (time.perf_counter() - started) * 1000
            _rate_limiter.record_active_user_response(
                result,
                model_name=settings.anthropic_xhigh_model,
                estimated_input_tokens=estimated_tokens,
            )
            _maybe_record_metric(
                messages=messages,
                response=result,
                model_name=settings.anthropic_xhigh_model,
                estimated_input_tokens=estimated_tokens,
                latency_ms=latency_ms,
            )
            return result
        except Exception as anthropic_error:
            raise RuntimeError(
                "XHIGH structured output failed for both OpenAI and Anthropic"
            ) from anthropic_error

    if openai_error is not None:
        raise openai_error

    raise RuntimeError(
        "OPENAI_API_KEY or ANTHROPIC_API_KEY is required for XHIGH-tier structured output"
    )
