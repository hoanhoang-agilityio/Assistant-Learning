from typing import Any

from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.research.graph import ResearchGraph
from core.subgraphs.research.research_agent import run_research_agent
from core.subgraphs.research.schema import ResearchAgentResult


class ResearchAgent:
    """LLM-driven Research Agent facade for the Research subgraph."""

    def __init__(self) -> None:
        self._graph = ResearchGraph()

    def run(self, orchestration_state: dict) -> dict:
        return self._graph.invoke_from_orchestration(orchestration_state)

    def run_agent(
        self,
        *,
        query: str,
        request_type: str | None,
        profile: dict[str, Any],
        execution_plan: ExecutionPlan,
    ) -> ResearchAgentResult:
        """Direct agent invocation for tests and tooling."""
        return run_research_agent(
            query=query,
            request_type=request_type,
            profile=profile,
            execution_plan=execution_plan,
        )
