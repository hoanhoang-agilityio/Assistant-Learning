"""Tests for LLM metrics collection."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from core.adapters.llm.factory import invoke_standard_llm
from core.adapters.llm.metrics import (
    get_llm_metrics_collector,
    reset_llm_metrics,
    reset_llm_metrics_node,
    set_llm_metrics_node,
    write_pipeline_cost_log,
)


def test_llm_metrics_collector_records_runtime_calls(monkeypatch) -> None:
    reset_llm_metrics()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from core.config.settings import get_settings

    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.content = "ok"
    mock_response.usage_metadata = {"input_tokens": 10, "output_tokens": 2}

    token = set_llm_metrics_node("planning_agent")
    try:
        with patch("core.adapters.llm.factory.get_standard_llm") as mock_get_llm:
            mock_get_llm.return_value.invoke.return_value = mock_response
            invoke_standard_llm([HumanMessage(content="hello")])
    finally:
        reset_llm_metrics_node(token)
        get_settings.cache_clear()

    collector = get_llm_metrics_collector()
    assert len(collector.metrics) == 1
    assert collector.metrics[0].node == "planning_agent"


def test_pipeline_cost_table_groups_nodes_and_writes_log(tmp_path) -> None:
    reset_llm_metrics()
    collector = get_llm_metrics_collector()
    from langchain_core.messages import HumanMessage

    from core.adapters.llm.metrics import record_llm_call_metric

    record_llm_call_metric(
        messages=[HumanMessage(content="extract")],
        response=MagicMock(usage_metadata={"input_tokens": 100, "output_tokens": 20}),
        model_name="gpt-4o-mini",
        estimated_input_tokens=100,
        latency_ms=10.0,
        node="profile_extraction",
    )
    record_llm_call_metric(
        messages=[HumanMessage(content="plan")],
        response=MagicMock(usage_metadata={"input_tokens": 200, "output_tokens": 80}),
        model_name="gpt-4o-mini",
        estimated_input_tokens=200,
        latency_ms=20.0,
        node="planning_agent",
    )
    record_llm_call_metric(
        messages=[HumanMessage(content="research")],
        response=MagicMock(usage_metadata={"input_tokens": 300, "output_tokens": 100}),
        model_name="gpt-4o-mini",
        estimated_input_tokens=300,
        latency_ms=30.0,
        node="research_synthesis",
    )

    rows = collector.pipeline_cost_table()
    extract_row = next(row for row in rows if row["node"] == "Extract")
    planning_row = next(row for row in rows if row["node"] == "Planning")
    research_row = next(row for row in rows if row["node"] == "Research")
    total_row = next(row for row in rows if row["node"] == "Total")

    assert extract_row["tokens"] == 120
    assert planning_row["tokens"] == 280
    assert research_row["tokens"] == 400
    assert total_row["tokens"] == 800
    assert extract_row["percent"] == 15.0
    assert planning_row["percent"] == 35.0
    assert research_row["percent"] == 50.0

    workspace = tmp_path / "run_test"
    workspace.mkdir()
    log_path = write_pipeline_cost_log(str(workspace), run_id="run_test")
    assert log_path.endswith("token_cost.log")
    content = (workspace / "logs" / "token_cost.log").read_text(encoding="utf-8")
    assert "Extract" in content
    assert "Total" in content
    assert "800" in content
