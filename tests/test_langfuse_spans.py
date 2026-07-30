"""Langfuse span naming tests."""

from core.adapters.observability.tracing import resolve_subgraph_span_name


def test_resolve_subgraph_span_name() -> None:
    assert resolve_subgraph_span_name("planning") == "Planning"
    assert resolve_subgraph_span_name("fitness") == "Fitness"
    assert resolve_subgraph_span_name("unknown") == "unknown"
