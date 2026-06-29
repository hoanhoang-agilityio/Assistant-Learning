from core.subgraphs.fitness.graph import FitnessGraph


class FitnessAgent:
    """LangGraph agent for Fitness subgraph."""

    def __init__(self) -> None:
        self._graph = FitnessGraph()

    def run(self, orchestration_state: dict) -> dict:
        return self._graph.invoke_from_orchestration(orchestration_state)
