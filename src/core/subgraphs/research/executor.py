"""Research capability executor.

Implements `core.orchestration.routing.executor.CapabilityExecutor`. Swappable via
`configure_research_executor` for a future LLM-driven ReAct executor without
touching `capability.py`, the dispatcher, or the graph.
"""

from __future__ import annotations

from uuid import uuid4

from core.orchestration.agents.execution_context import CapabilityResult, ExecutionContext
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.routing.executor import CapabilityExecutor
from core.planning.schema import ExecutionPlan, PlanTask
from core.shared.profile.goal_spec import derive_goal_spec
from core.subgraphs.research.research_agent import run_research_agent
from core.subgraphs.research.schema import ResearchFindings
from core.subgraphs.research.utils import (
    load_execution_plan_for_research,
    load_profile_for_research,
    write_research_artifacts,
)


def _minimal_research_plan(query: str) -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale="Direct research question without prior planning output.",
        tasks=[
            PlanTask(
                order=1, task=f"Research evidence for: {query[:200]}", rationale="User question"
            ),
            PlanTask(order=2, task="Find consensus guidelines", rationale="Evidence synthesis"),
            PlanTask(order=3, task="Summarize actionable findings", rationale="Answer delivery"),
        ],
        plan_markdown=f"# Research plan\n\nInvestigate: {query}",
    )


class SupervisorRoutedResearchExecutor:
    """AgentResult-only Research executor for the hybrid Supervisor routing design
    (see docs/reports plan). Research has always been a "resume the caller" step --
    it never decides what runs next."""

    def execute(self, state: OrchestrationState, ctx: ExecutionContext | None) -> CapabilityResult:
        workspace = state["workspace_path"]
        query = state.get("fitness_query") or state["query"]
        profile = load_profile_for_research(workspace) or {}
        goal_spec = derive_goal_spec(profile)
        execution_plan = load_execution_plan_for_research(workspace)
        if execution_plan is None:
            execution_plan = _minimal_research_plan(query)
        agent_result = run_research_agent(
            query=query,
            profile=profile,
            goal_spec=goal_spec,
            execution_plan=execution_plan,
            workspace_path=workspace,
            is_reresearch=False,
            # L1 Phase 4: set only when the Policy Engine routed here via
            # verification_failed_auto_retry (verification/capability.py lifts
            # it from the failed report); None on a first pass or any other
            # entry into Research.
            verification_feedback=state.get("verification_feedback"),
        )
        write_research_artifacts(
            workspace_path=workspace,
            sources=agent_result.sources,
            evidence=agent_result.evidence,
            structured_findings=agent_result.structured_findings,
            evidence_summary=agent_result.evidence_summary,
        )
        if ctx and ctx.intent == "research_question":
            return CapabilityResult(
                request_id=uuid4(),
                capability="research",
                status="completed",
                summary=agent_result.evidence_summary,
            )
        return CapabilityResult(
            request_id=uuid4(),
            capability="research",
            status="completed",
            summary=agent_result.evidence_summary,
            artifacts={
                "structured_findings": ResearchFindings.model_validate(
                    agent_result.structured_findings.model_dump()
                ).model_dump(),
                "evidence_summary": agent_result.evidence_summary,
            },
        )


_executor: CapabilityExecutor = SupervisorRoutedResearchExecutor()


def configure_research_executor(executor: CapabilityExecutor | None) -> None:
    """Override the Research capability executor (used in tests, or to swap
    in a future ReAct agent)."""
    global _executor
    _executor = executor or SupervisorRoutedResearchExecutor()


def get_research_executor() -> CapabilityExecutor:
    return _executor
