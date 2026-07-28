"""Deterministic Research capability executor.

Implements `core.capabilities.executor.CapabilityExecutor`. Swappable via
`configure_research_executor` for a future LLM-driven ReAct executor without
touching `capability.py`, the dispatcher, or the graph.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from core.agents.execution_context import CapabilityResult, ExecutionContext
from core.agents.state import OrchestrationState
from core.capabilities.executor import CapabilityExecutor
from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.research.research_agent import run_research_agent
from core.subgraphs.research.schema import ResearchFindings
from core.subgraphs.research.utils import (
    load_execution_plan_for_research,
    load_profile_for_research,
    write_research_artifacts,
)


def _request_id(state: OrchestrationState) -> UUID:
    pending = state.get("pending_request")
    if pending:
        return UUID(pending["request_id"])
    return uuid4()


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


class DeterministicResearchExecutor:
    """Always runs the full retrieve -> verify -> synthesize pipeline via
    `run_research_agent` -- no reasoning about which retrieval step to skip."""

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
                request_id=_request_id(state),
                capability="research",
                status="completed",
                output={
                    "final_response": agent_result.evidence_summary,
                    "run_complete": True,
                },
            )
        return CapabilityResult(
            request_id=_request_id(state),
            capability="research",
            status="completed",
            output={
                "structured_findings": ResearchFindings.model_validate(
                    agent_result.structured_findings.model_dump()
                ).model_dump(),
                "evidence_summary": agent_result.evidence_summary,
            },
        )


class SupervisorRoutedResearchExecutor:
    """AgentResult-only Research executor for the hybrid Supervisor routing design
    (see docs/reports plan). Same retrieve -> verify -> synthesize pipeline as
    `DeterministicResearchExecutor` -- it never decided what runs next even in the
    old design (Research has always been a "resume the caller" step), so this is a
    field-mapping-only change."""

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
