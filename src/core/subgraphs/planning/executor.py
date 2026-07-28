"""Deterministic Planning capability executor.

Implements `core.capabilities.executor.CapabilityExecutor`. Planning owns
goal specification only: it computes from the validated profile + request,
never calculates macros, retrieves evidence, selects exercises, or generates
workouts. Swappable via `configure_planning_executor` for a future
LLM-assisted executor without touching `capability.py`, the dispatcher, or
the graph.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core.agents.execution_context import CapabilityResult, ExecutionContext
from core.agents.state import OrchestrationState
from core.capabilities.dispatcher import make_capability_request
from core.capabilities.executor import CapabilityExecutor
from core.profile.goal_spec import derive_goal_spec
from core.profile.store import load_run_profile, split_constraints
from core.subgraphs.planning.output import PlanningOutput
from core.vfs import VFS
from core.vfs.layout import PLAN_MARKDOWN

PLANNING_OUTPUT_PATH = "plan/planning_output.json"


def build_planning_output(workspace_path: str, query: str) -> PlanningOutput:
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)
    return PlanningOutput(
        goal=str(profile.get("goal", "general_fitness")),
        constraints={
            "days_per_week": int(
                profile.get("days_per_week") or constraints.get("days_per_week", 3)
            ),
            "equipment": str(constraints.get("equipment", "gym")),
            "session_duration_minutes": int(constraints.get("session_duration_minutes", 60)),
            "feasibility_level": goal_spec.feasibility_level,
        },
        preferences={
            "high_protein": bool(constraints.get("high_protein", False)),
            "goal_archetype": goal_spec.goal_archetype,
        },
        training_requirements={
            "horizon_weeks": profile.get("horizon_weeks") or 0,
            "weekly_rate_kg": goal_spec.weekly_rate_kg or 0.0,
            "query_focus": query[:500],
        },
        summary_markdown=(
            f"## Goal specification\n\n"
            f"- Goal: {profile.get('goal', 'general_fitness')}\n"
            f"- Days per week: {profile.get('days_per_week', constraints.get('days_per_week', 3))}\n"
            f"- Equipment: {constraints.get('equipment', 'gym')}\n"
            f"- Feasibility: {goal_spec.feasibility_level}\n"
        ),
    )


def persist_planning_output(workspace_path: str, output: PlanningOutput) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write(PLANNING_OUTPUT_PATH, output.model_dump_json(indent=2))
    vfs.write(PLAN_MARKDOWN, output.summary_markdown)


class DeterministicPlanningExecutor:
    """Computes PlanningOutput straight from the validated profile -- no LLM call."""

    def execute(self, state: OrchestrationState, ctx: ExecutionContext | None) -> CapabilityResult:
        workspace = state["workspace_path"]
        query = state.get("fitness_query") or state["query"]
        output = build_planning_output(workspace, query)
        persist_planning_output(workspace, output)
        request_id = uuid4()
        if state.get("resume_capability"):
            return CapabilityResult(
                request_id=request_id,
                capability="planning",
                status="completed",
                output={"planning_output_path": PLANNING_OUTPUT_PATH},
                next_request=None,
            )
        return CapabilityResult(
            request_id=request_id,
            capability="planning",
            status="needs_capability",
            output={"planning_output_path": PLANNING_OUTPUT_PATH},
            next_request=make_capability_request(
                capability="fitness",
                reason="Goal specification complete",
                payload={"planning_output_path": PLANNING_OUTPUT_PATH},
            ),
        )


class SupervisorRoutedPlanningExecutor:
    """AgentResult-only Planning executor for the hybrid Supervisor routing design
    (see docs/reports plan). Same goal-specification computation as
    `DeterministicPlanningExecutor` -- it never decides what runs next; the
    Supervisor + Policy Engine route to Fitness from here."""

    def execute(self, state: OrchestrationState, ctx: ExecutionContext | None) -> CapabilityResult:
        workspace = state["workspace_path"]
        query = state.get("fitness_query") or state["query"]
        output = build_planning_output(workspace, query)
        persist_planning_output(workspace, output)
        return CapabilityResult(
            request_id=uuid4(),
            capability="planning",
            status="completed",
            summary="Goal specification complete.",
            artifacts={"planning_output_path": PLANNING_OUTPUT_PATH},
        )


_executor: CapabilityExecutor = SupervisorRoutedPlanningExecutor()


def configure_planning_executor(executor: CapabilityExecutor | None) -> None:
    """Override the Planning capability executor (used in tests, or to swap
    in a future LLM-assisted executor)."""
    global _executor
    _executor = executor or SupervisorRoutedPlanningExecutor()


def get_planning_executor() -> CapabilityExecutor:
    return _executor
