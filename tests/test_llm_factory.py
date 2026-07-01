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
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = expected
    mock_get_openai.return_value.with_structured_output.return_value = structured_llm

    result = invoke_xhigh_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_openai.assert_called_once()
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

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = RuntimeError("openai unavailable")
    mock_get_openai.return_value.with_structured_output.return_value = openai_structured

    anthropic_structured = MagicMock()
    anthropic_structured.invoke.return_value = expected
    mock_get_anthropic.return_value.with_structured_output.return_value = anthropic_structured

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

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = RuntimeError("openai unavailable")
    mock_get_openai.return_value.with_structured_output.return_value = openai_structured

    anthropic_structured = MagicMock()
    anthropic_structured.invoke.side_effect = RuntimeError("anthropic unavailable")
    mock_get_anthropic.return_value.with_structured_output.return_value = anthropic_structured

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

    openai_structured = MagicMock()
    openai_structured.invoke.side_effect = ValueError("validation error: invalid schema")
    mock_get_openai.return_value.with_structured_output.return_value = openai_structured

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
    mock_get_standard.return_value.with_structured_output.return_value = structured_llm

    result = invoke_standard_structured_output(ExecutionPlan, [])

    assert result == expected
    mock_get_standard.assert_called_once()
