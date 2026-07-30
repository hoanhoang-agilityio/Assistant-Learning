from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot

from core.orchestration.agents.state import OrchestrationState
from core.subgraphs.user.graph import invoke_user_subgraph


def _build_standalone_wrapper() -> CompiledStateGraph:
    """Wrap the User subgraph in a single-node parent graph with its own checkpointer.

    The User subgraph is compiled with ``checkpointer=True`` (see ``build_user_subgraph``),
    which LangGraph only allows when nested inside a parent graph that owns a real
    checkpointer -- it cannot be invoked as a root graph on its own. This wrapper exists so
    ``UserAgent`` can run/resume the subgraph standalone (tests, tooling), matching how the
    other four subgraphs' ``XAgent`` facades work, without requiring the full supervisor graph.
    """
    graph = StateGraph(OrchestrationState)
    graph.add_node("user", invoke_user_subgraph)
    graph.add_edge(START, "user")
    graph.add_edge("user", END)
    return graph.compile(checkpointer=MemorySaver())


class UserAgent:
    """Facade for the User subgraph (profile intake/extraction/validation)."""

    def __init__(self) -> None:
        self._graph = _build_standalone_wrapper()

    def _config(self, orchestration_state: dict) -> dict[str, Any]:
        thread_id = orchestration_state.get("thread_id") or orchestration_state.get("run_id")
        if not thread_id:
            raise ValueError("orchestration_state must include thread_id or run_id")
        return {"configurable": {"thread_id": thread_id}}

    def run(self, orchestration_state: dict) -> dict:
        """Run the User subgraph to completion or its first pause."""
        return self._graph.invoke(orchestration_state, self._config(orchestration_state))

    def resume(self, orchestration_state: dict, form_data: dict[str, Any]) -> dict:
        """Resume a run paused at the profile form with submitted form data."""
        return self._graph.invoke(Command(resume=form_data), self._config(orchestration_state))

    def get_state(self, orchestration_state: dict) -> StateSnapshot:
        """Inspect the paused/completed state for the given run's thread."""
        return self._graph.get_state(self._config(orchestration_state))
