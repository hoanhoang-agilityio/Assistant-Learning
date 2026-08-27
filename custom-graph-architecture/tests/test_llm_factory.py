"""Tests for the one model construction site and the one retry policy.

The rules these hold: no call site builds its own model, no permanent failure is retried,
and the retry budget is a setting rather than a number someone typed into a node.
"""

from pathlib import Path

import httpx
import pytest
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.runnables import RunnableLambda
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from src.core.configs.config import settings
from src.core.llm import (
    RETRYABLE_ERRORS,
    agent_middleware,
    chat_model,
    embedding_model,
    with_retry_policy,
)

SRC = Path(__file__).resolve().parent.parent / "src"
FACTORY = SRC / "core" / "llm.py"

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.fixture(autouse=True)
def uncached() -> None:
    """The factory caches per configuration; no test may leave a model behind."""
    chat_model.cache_clear()
    embedding_model.cache_clear()
    yield
    chat_model.cache_clear()
    embedding_model.cache_clear()


# --- One construction site ----------------------------------------------------------------


def test_the_factory_is_the_only_place_a_model_is_constructed() -> None:
    """A second construction site is a second place the model name can quietly drift."""
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if path != FACTORY and "langchain_openai import" in path.read_text()
    ]

    assert offenders == []


def test_the_configured_model_and_ceiling_are_the_ones_built() -> None:
    """A hardcoded model is a deployment setting nobody can turn without a release."""
    model = chat_model(max_tokens=1234)

    assert model._default_params["model"] == settings.DEFAULT_LLM_MODEL
    assert model._default_params["max_completion_tokens"] == 1234


def test_the_sdks_own_retries_are_off_so_one_policy_governs() -> None:
    """Left on, a run carries two retry policies stacked and the attempt counts mean neither."""
    assert chat_model().max_retries == 0


def test_one_configuration_builds_one_model() -> None:
    """A model per call would rebuild an HTTP client on every turn."""
    assert chat_model() is chat_model()
    assert chat_model(max_tokens=99) is not chat_model()


def test_the_embedding_model_matches_the_stored_vector_width() -> None:
    """A dimension mismatch is not a failure at write time; it is silently wrong retrieval."""
    embedder = embedding_model()

    assert embedder.model == settings.KNOWLEDGE_EMBEDDER_MODEL
    assert embedder.dimensions == settings.KNOWLEDGE_EMBEDDING_DIM


# --- What is worth retrying ---------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        RateLimitError(
            "slow down", response=httpx.Response(429, request=REQUEST), body=None
        ),
        APITimeoutError(request=REQUEST),
        APIConnectionError(request=REQUEST),
        InternalServerError(
            "boom", response=httpx.Response(500, request=REQUEST), body=None
        ),
    ],
)
def test_a_transient_failure_is_retryable(error: Exception) -> None:
    """These are the failures a later attempt against the same model can survive."""
    assert isinstance(error, RETRYABLE_ERRORS)


@pytest.mark.parametrize(
    "error",
    [
        BadRequestError(
            "bad schema", response=httpx.Response(400, request=REQUEST), body=None
        ),
        AuthenticationError(
            "bad key", response=httpx.Response(401, request=REQUEST), body=None
        ),
    ],
)
def test_a_permanent_failure_is_not_retryable(error: Exception) -> None:
    """A malformed request and a bad key fail identically every attempt; retrying hides why."""
    assert not isinstance(error, RETRYABLE_ERRORS)


async def test_a_transient_failure_is_retried_up_to_the_configured_budget() -> None:
    """The budget is a setting, so a noisy provider is a config change and not a release."""
    attempts = 0

    async def flaky(_input: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < settings.MAX_LLM_CALL_RETRIES:
            raise APITimeoutError(request=REQUEST)
        return "ok"

    assert await with_retry_policy(RunnableLambda(flaky)).ainvoke("go") == "ok"
    assert attempts == settings.MAX_LLM_CALL_RETRIES


async def test_a_permanent_failure_costs_exactly_one_attempt() -> None:
    """Retrying something that can never succeed only delays the error the caller needs."""
    attempts = 0

    async def broken(_input: str) -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("malformed schema")

    with pytest.raises(ValueError):
        await with_retry_policy(RunnableLambda(broken)).ainvoke("go")

    assert attempts == 1


# --- The policy every agent runs under ----------------------------------------------------


def test_every_agent_retries_the_model_the_tool_and_bounds_its_loop() -> None:
    """Spec §9 asks for all three; a missing one is a failure mode with no handling."""
    kinds = {type(middleware) for middleware in agent_middleware()}

    assert kinds == {
        ModelRetryMiddleware,
        ToolRetryMiddleware,
        ModelCallLimitMiddleware,
    }


def test_an_exhausted_model_retry_raises_rather_than_answering_with_the_error() -> None:
    """An error dressed as an answer would walk straight through the verification gate."""
    [model_retry] = [
        m for m in agent_middleware() if isinstance(m, ModelRetryMiddleware)
    ]

    assert model_retry.on_failure == "error"
    assert model_retry.retry_on == RETRYABLE_ERRORS


def test_the_model_retry_budget_counts_attempts_not_retries() -> None:
    """The middleware counts retries after the first call; the setting counts attempts."""
    [model_retry] = [
        m for m in agent_middleware() if isinstance(m, ModelRetryMiddleware)
    ]

    assert model_retry.max_retries == settings.MAX_LLM_CALL_RETRIES - 1


def test_an_exhausted_tool_retry_is_handed_back_to_the_model_to_work_around() -> None:
    """A catalogue lookup the agent cannot reach is something it can plan around."""
    [tool_retry] = [m for m in agent_middleware() if isinstance(m, ToolRetryMiddleware)]

    assert tool_retry.on_failure == "continue"
    assert tool_retry.max_retries == settings.TOOL_MAX_RETRIES
