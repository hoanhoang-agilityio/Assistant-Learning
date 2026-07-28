"""Tests for XHIGH LLM factory fallback behavior."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from core.config.settings import Settings
from core.llm.factory import (
    configure_rate_limiter,
    get_standard_llm,
    get_xhigh_anthropic_llm,
    get_xhigh_openai_llm,
    invoke_standard_structured_output,
    invoke_xhigh_structured_output,
)
from core.planning.schema import ExecutionPlan, PlanTask
from core.rate_limit import AIRateLimiter, InMemoryUsageStore
from core.rate_limit.context import reset_rate_limit_user_id, set_rate_limit_user_id

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def _include_raw_result(parsed: ExecutionPlan, *, output_tokens: int = 42) -> dict:
    """Simulate with_structured_output(..., include_raw=True).invoke()'s return shape."""
    raw = AIMessage(
        content="",
        usage_metadata={
            "input_tokens": 123,
            "output_tokens": output_tokens,
            "total_tokens": 123 + output_tokens,
        },
    )
    return {"raw": raw, "parsed": parsed, "parsing_error": None}


def _sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale=_MIN_PLAN_RATIONALE,
        tasks=[
            PlanTask(
                order=1,
                task="Research fat loss training volume",
                rationale="Volume must match 3x/week gym schedule",
            ),
            PlanTask(
                order=2,
                task="Research protein intake during fat loss",
                rationale="Protein supports lean mass retention while cutting",
            ),
            PlanTask(
                order=3,
                task="Verify credibility of selected fat loss sources",
                rationale="Downstream synthesis needs trustworthy evidence",
            ),
        ],
        plan_markdown=_MIN_PLAN_MARKDOWN,
    )


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_xhigh_anthropic_llm")
@patch("core.llm.factory.get_xhigh_openai_llm")
def test_invoke_xhigh_structured_output_uses_openai_first(
    mock_get_openai: MagicMock,
    mock_get_anthropic: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    expected = _sample_plan()
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.anthropic_api_key = "anthropic-key"
    mock_get_settings.return_value.llm_structured_output_max_tokens = 2048
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = _include_raw_result(expected)
    bound_llm = MagicMock()
    bound_llm.with_structured_output.return_value = structured_llm
    mock_get_openai.return_value.bind.return_value = bound_llm

    result = invoke_xhigh_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_openai.assert_called_once()
    mock_get_openai.return_value.bind.assert_called_once_with(max_tokens=2048)
    bound_llm.with_structured_output.assert_called_once_with(
        ExecutionPlan,
        method="json_schema",
        include_raw=True,
    )
    mock_get_anthropic.assert_not_called()


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_xhigh_anthropic_llm")
@patch("core.llm.factory.get_xhigh_openai_llm")
def test_invoke_xhigh_structured_output_falls_back_to_anthropic(
    mock_get_openai: MagicMock,
    mock_get_anthropic: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    expected = _sample_plan()
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.anthropic_api_key = "anthropic-key"
    mock_get_settings.return_value.llm_structured_output_max_tokens = 2048

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = RuntimeError("openai unavailable")
    openai_bound = MagicMock()
    openai_bound.with_structured_output.return_value = openai_structured
    mock_get_openai.return_value.bind.return_value = openai_bound

    anthropic_structured = MagicMock()
    anthropic_structured.invoke.return_value = _include_raw_result(expected)
    anthropic_bound = MagicMock()
    anthropic_bound.with_structured_output.return_value = anthropic_structured
    mock_get_anthropic.return_value.bind.return_value = anthropic_bound

    result = invoke_xhigh_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_openai.assert_called_once()
    mock_get_anthropic.assert_called_once()
    anthropic_bound.with_structured_output.assert_called_once_with(
        ExecutionPlan,
        method="function_calling",
        include_raw=True,
    )


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_xhigh_anthropic_llm")
@patch("core.llm.factory.get_xhigh_openai_llm")
def test_invoke_xhigh_structured_output_raises_when_both_providers_fail(
    mock_get_openai: MagicMock,
    mock_get_anthropic: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.anthropic_api_key = "anthropic-key"
    mock_get_settings.return_value.llm_structured_output_max_tokens = 2048

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = RuntimeError("openai unavailable")
    openai_bound = MagicMock()
    openai_bound.with_structured_output.return_value = openai_structured
    mock_get_openai.return_value.bind.return_value = openai_bound

    anthropic_structured = MagicMock()
    anthropic_structured.invoke.side_effect = RuntimeError("anthropic unavailable")
    anthropic_bound = MagicMock()
    anthropic_bound.with_structured_output.return_value = anthropic_structured
    mock_get_anthropic.return_value.bind.return_value = anthropic_bound

    with pytest.raises(RuntimeError, match="failed for both OpenAI and Anthropic"):
        invoke_xhigh_structured_output(ExecutionPlan, [])


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_xhigh_anthropic_llm")
@patch("core.llm.factory.get_xhigh_openai_llm")
def test_invoke_xhigh_structured_output_skips_fallback_for_non_transient_errors(
    mock_get_openai: MagicMock,
    mock_get_anthropic: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.anthropic_api_key = "anthropic-key"
    mock_get_settings.return_value.llm_structured_output_max_tokens = 2048

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = ValueError("validation error: invalid schema")
    openai_bound = MagicMock()
    openai_bound.with_structured_output.return_value = openai_structured
    mock_get_openai.return_value.bind.return_value = openai_bound

    with pytest.raises(ValueError, match="validation error"):
        invoke_xhigh_structured_output(ExecutionPlan, [])

    mock_get_openai.assert_called_once()
    mock_get_anthropic.assert_not_called()


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_standard_llm")
def test_invoke_standard_structured_output(
    mock_get_standard: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    expected = _sample_plan()
    mock_get_settings.return_value.openai_api_key = "openai-key"
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = _include_raw_result(expected)
    bound_llm = MagicMock()
    bound_llm.with_structured_output.return_value = structured_llm
    mock_get_standard.return_value.bind.return_value = bound_llm

    result = invoke_standard_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_standard.assert_called_once()


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_xhigh_anthropic_llm")
@patch("core.llm.factory.get_xhigh_openai_llm")
def test_invoke_xhigh_structured_output_skips_fallback_for_length_limit_errors(
    mock_get_openai: MagicMock,
    mock_get_anthropic: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.anthropic_api_key = "anthropic-key"
    mock_get_settings.return_value.llm_structured_output_max_tokens = 2048

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = ValueError(
        "Could not parse response content as the length limit was reached"
    )
    openai_bound = MagicMock()
    openai_bound.with_structured_output.return_value = openai_structured
    mock_get_openai.return_value.bind.return_value = openai_bound

    with pytest.raises(ValueError, match="length limit"):
        invoke_xhigh_structured_output(ExecutionPlan, [])

    mock_get_anthropic.assert_not_called()


@patch("core.llm.factory.get_settings")
@patch("core.llm.factory.get_standard_llm")
def test_invoke_standard_structured_output_meters_real_output_tokens(
    mock_get_standard: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    """Regression test for A4: with_structured_output(...).invoke() returns a parsed
    Pydantic object with no usage_metadata of its own. Metering that object (instead of
    the raw AIMessage returned alongside it via include_raw=True) silently fabricates an
    input-token estimate and reports 0 output tokens -- defeating the per-user daily
    cost/token cap for every structured-output call. Assert the real usage from the raw
    message (777 output tokens, not 0) is what actually reaches the rate limiter."""
    expected = _sample_plan()
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.openai_standard_model = "gpt-5.4-mini"
    mock_get_settings.return_value.llm_structured_output_max_tokens = 2048
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = _include_raw_result(expected, output_tokens=777)
    bound_llm = MagicMock()
    bound_llm.with_structured_output.return_value = structured_llm
    mock_get_standard.return_value.bind.return_value = bound_llm

    settings = Settings(rate_limit_enabled=True, rate_limit_daily_max_tokens_per_user=1_000_000)
    limiter = AIRateLimiter(settings=settings, store=InMemoryUsageStore())
    configure_rate_limiter(limiter)
    token = set_rate_limit_user_id("metering-test-user")
    try:
        invoke_standard_structured_output(ExecutionPlan, [])
        snapshot = limiter.get_snapshot("metering-test-user")
    finally:
        reset_rate_limit_user_id(token)
        configure_rate_limiter(None)

    assert snapshot.output_tokens == 777
    assert snapshot.input_tokens == 123


@patch("core.llm.factory.ChatOpenAI")
@patch("core.llm.factory.get_settings")
def test_get_standard_llm_configures_request_timeout(
    mock_get_settings: MagicMock,
    mock_chat_openai: MagicMock,
) -> None:
    """Regression (PR2): the STANDARD-tier OpenAI client must carry an explicit
    deadline so a hung provider connection can never block a run indefinitely."""
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.openai_standard_model = "gpt-5.4-mini"
    mock_get_settings.return_value.openai_max_tokens = 4096
    mock_get_settings.return_value.openai_standard_reasoning_effort = "none"
    mock_get_settings.return_value.openai_verbosity = "low"
    mock_get_settings.return_value.openai_standard_timeout_seconds = 60.0

    get_standard_llm.cache_clear()
    try:
        get_standard_llm()
    finally:
        get_standard_llm.cache_clear()

    mock_chat_openai.assert_called_once_with(
        model="gpt-5.4-mini",
        api_key="openai-key",
        max_tokens=4096,
        reasoning_effort="none",
        verbosity="low",
        timeout=60.0,
        temperature=0,
    )


@patch("core.llm.factory.ChatOpenAI")
@patch("core.llm.factory.get_settings")
def test_get_xhigh_openai_llm_configures_request_timeout(
    mock_get_settings: MagicMock,
    mock_chat_openai: MagicMock,
) -> None:
    """Regression (PR2): the XHIGH-tier OpenAI client must carry an explicit
    deadline, independent of the STANDARD tier's own timeout setting."""
    mock_get_settings.return_value.openai_api_key = "openai-key"
    mock_get_settings.return_value.openai_xhigh_model = "gpt-5.4"
    mock_get_settings.return_value.openai_max_tokens = 4096
    mock_get_settings.return_value.openai_xhigh_reasoning_effort = "low"
    mock_get_settings.return_value.openai_verbosity = "low"
    mock_get_settings.return_value.openai_xhigh_timeout_seconds = 90.0

    get_xhigh_openai_llm.cache_clear()
    try:
        get_xhigh_openai_llm()
    finally:
        get_xhigh_openai_llm.cache_clear()

    mock_chat_openai.assert_called_once_with(
        model="gpt-5.4",
        api_key="openai-key",
        max_tokens=4096,
        reasoning_effort="low",
        verbosity="low",
        timeout=90.0,
    )


@patch("core.llm.factory.ChatAnthropic")
@patch("core.llm.factory.get_settings")
def test_get_xhigh_anthropic_llm_configures_request_timeout(
    mock_get_settings: MagicMock,
    mock_chat_anthropic: MagicMock,
) -> None:
    """Regression (PR2): the Anthropic fallback client must carry an explicit
    deadline too -- a hung fallback call is just as capable of stalling a run."""
    mock_get_settings.return_value.anthropic_api_key = "anthropic-key"
    mock_get_settings.return_value.anthropic_xhigh_model = "claude-3-5-haiku-20241022"
    mock_get_settings.return_value.anthropic_max_tokens = 4096
    mock_get_settings.return_value.anthropic_timeout_seconds = 90.0

    get_xhigh_anthropic_llm.cache_clear()
    try:
        get_xhigh_anthropic_llm()
    finally:
        get_xhigh_anthropic_llm.cache_clear()

    mock_chat_anthropic.assert_called_once_with(
        model="claude-3-5-haiku-20241022",
        api_key="anthropic-key",
        temperature=0,
        max_tokens=4096,
        timeout=90.0,
    )
