"""Tests for XHIGH LLM factory fallback behavior."""

from unittest.mock import MagicMock, patch

import pytest

from core.llm.factory import invoke_standard_structured_output, invoke_xhigh_structured_output
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


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
    structured_llm.invoke.return_value = expected
    bound_llm = MagicMock()
    bound_llm.with_structured_output.return_value = structured_llm
    mock_get_openai.return_value.bind.return_value = bound_llm

    result = invoke_xhigh_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_openai.assert_called_once()
    mock_get_openai.return_value.bind.assert_called_once_with(max_tokens=2048)
    bound_llm.with_structured_output.assert_called_once_with(
        ExecutionPlan,
        method="function_calling",
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
    anthropic_structured.invoke.return_value = expected
    anthropic_bound = MagicMock()
    anthropic_bound.with_structured_output.return_value = anthropic_structured
    mock_get_anthropic.return_value.bind.return_value = anthropic_bound

    result = invoke_xhigh_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_openai.assert_called_once()
    mock_get_anthropic.assert_called_once()


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
    structured_llm.invoke.return_value = expected
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
