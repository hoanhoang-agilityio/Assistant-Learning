"""The one place a model is constructed, and the one retry policy every call shares."""

from functools import lru_cache

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from src.core.configs.config import settings

# Transient only: a later attempt against the same model can succeed. The rest of the
# OpenAI hierarchy — 400 bad request, 401 auth, 404 — fails identically every time, so
# retrying it only delays the error and buries its cause under retry logs.
RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


@lru_cache
def chat_model(
    model: str | None = None, max_tokens: int | None = None
) -> BaseChatModel:
    """The chat model for one call site, built once per distinct configuration."""

    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=model or settings.DEFAULT_LLM_MODEL,
        max_completion_tokens=max_tokens or settings.MAX_TOKENS,
        timeout=settings.LLM_TOTAL_TIMEOUT,
        # The OpenAI SDK retries transient failures on its own. Left on, a run would carry
        # two retry policies stacked — the SDK's inside ours — and the attempt counts in
        # the logs would mean neither one.
        max_retries=0,
    )


@lru_cache
def embedding_model() -> OpenAIEmbeddings:
    """The embedding model, shared by the knowledge seeder and by retrieval."""

    return OpenAIEmbeddings(
        model=settings.KNOWLEDGE_EMBEDDER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        dimensions=settings.KNOWLEDGE_EMBEDDING_DIM,
    )


def with_retry_policy(runnable: Runnable) -> Runnable:
    """Put a plain, non-agent model call under the shared retry policy."""

    return runnable.with_retry(
        retry_if_exception_type=RETRYABLE_ERRORS,
        stop_after_attempt=settings.MAX_LLM_CALL_RETRIES,
        wait_exponential_jitter=True,
    )


def agent_middleware() -> list[AgentMiddleware]:
    """The error policy every agent runs under: retry the model, retry the tool, bound the loop."""

    return [
        ModelRetryMiddleware(
            max_retries=settings.MAX_LLM_CALL_RETRIES - 1,
            retry_on=RETRYABLE_ERRORS,
            # Raise rather than answer with the error text: the node catches it and the
            # graph's own gate counts the failure, which is where the retry budget for a
            # whole plan lives. An error dressed up as an answer would pass that gate.
            on_failure="error",
        ),
        ToolRetryMiddleware(
            max_retries=settings.TOOL_MAX_RETRIES,
            # A tool the model can no longer reach is something it can work around —
            # ask for a different template, plan without the catalogue lookup. Handing
            # the failure back as a tool message is what lets it.
            on_failure="continue",
        ),
        ModelCallLimitMiddleware(
            run_limit=settings.AGENT_MAX_MODEL_CALLS,
            exit_behavior="end",
        ),
    ]


__all__ = [
    "RETRYABLE_ERRORS",
    "agent_middleware",
    "chat_model",
    "embedding_model",
    "with_retry_policy",
]
