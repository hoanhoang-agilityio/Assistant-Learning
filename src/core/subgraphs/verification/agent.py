from core.subgraphs.verification.graph import VerificationGraph


class VerificationAgent:
    """LangGraph agent for Verification subgraph."""

    def __init__(self) -> None:
        self._graph = VerificationGraph()

    def run(self, orchestration_state: dict) -> dict:
        return self._graph.invoke_from_orchestration(orchestration_state)
