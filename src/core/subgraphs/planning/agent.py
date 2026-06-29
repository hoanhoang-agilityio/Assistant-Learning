from core.subgraphs.planning.graph import PlanningGraph


class PlanningAgent:
    """LangGraph agent for Planning subgraph."""

    def __init__(self) -> None:
        self._graph = PlanningGraph()

    def run(self, orchestration_state: dict) -> dict:
        return self._graph.invoke_from_orchestration(orchestration_state)
