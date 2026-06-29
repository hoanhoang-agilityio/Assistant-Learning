from core.subgraphs.research.graph import ResearchGraph


class ResearchAgent:
    """LangGraph agent for Research subgraph."""

    def __init__(self) -> None:
        self._graph = ResearchGraph()

    def run(self, orchestration_state: dict) -> dict:
        return self._graph.invoke_from_orchestration(orchestration_state)
