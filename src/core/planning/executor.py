"""Planning capability executor.

Implements `core.orchestration.routing.executor.CapabilityExecutor`. Planning owns
goal specification only: it computes from the validated profile + request,
never calculates macros, retrieves evidence, selects exercises, or generates
workouts. Swappable via `configure_planning_executor` for a future
LLM-assisted executor without touching `node.py`, the dispatcher, or
the graph.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core.orchestration.agents.execution_context import CapabilityResult, ExecutionContext
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.routing.executor import CapabilityExecutor
from core.planning.output import PlanningOutput
from core.planning.schema import ExecutionPlan, PlanTask
from core.shared.profile.goal_spec import derive_goal_spec
from core.shared.profile.store import load_run_profile, split_constraints
from core.vfs import VFS
from core.vfs.layout import PLAN_EXECUTION_PLAN, PLAN_MARKDOWN

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


def build_execution_plan(workspace_path: str) -> ExecutionPlan:
    """Deterministic goal-spec-derived research task list -- no LLM call, mirroring
    build_planning_output's own derivation. Gives Research/Fitness a real per-run
    execution plan instead of silently falling back to Research's generic
    `_minimal_research_plan` default or Fitness's `execution_plan=None` path.
    """
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)

    goal = str(profile.get("goal", "general_fitness"))
    equipment = str(constraints.get("equipment", "gym"))
    days_per_week = int(profile.get("days_per_week") or constraints.get("days_per_week", 3))
    horizon_weeks = profile.get("horizon_weeks") or "an unspecified number of"
    weekly_rate = goal_spec.weekly_rate_kg
    rate_desc = f"{weekly_rate} kg/week" if weekly_rate is not None else "a maintenance pace"

    tasks = [
        PlanTask(
            order=1,
            task=(
                f"Find evidence-based training split guidance for {days_per_week} "
                f"days/week with {equipment} equipment."
            ),
            rationale=(
                "Grounds exercise selection and weekly split in the user's actual "
                "training frequency and available equipment."
            ),
        ),
        PlanTask(
            order=2,
            task=(
                f"Find nutrition guidelines supporting a {goal_spec.goal_archetype} "
                f"goal at {rate_desc}."
            ),
            rationale=(
                "Grounds macro targets in evidence matching the user's goal direction and pace."
            ),
        ),
        PlanTask(
            order=3,
            task=(
                f"Find safety considerations for a {goal} goal with "
                f"{goal_spec.feasibility_level} feasibility over {horizon_weeks} weeks."
            ),
            rationale=(
                "Surfaces cautions the plan should account for given the assessed feasibility."
            ),
        ),
    ]
    plan_markdown = "\n".join(
        [
            "## Execution Plan",
            "",
            f"- Goal archetype: {goal_spec.goal_archetype}",
            f"- Feasibility: {goal_spec.feasibility_level}",
            "",
            *(f"{task.order}. {task.task}" for task in tasks),
        ]
    )
    return ExecutionPlan(
        plan_rationale=(
            f"Deterministic goal-spec-derived research plan for a {goal_spec.goal_archetype} "
            f"goal ({goal_spec.feasibility_level} feasibility)."
        ),
        tasks=tasks,
        plan_markdown=plan_markdown,
    )


def persist_execution_plan(workspace_path: str, plan: ExecutionPlan) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write(PLAN_EXECUTION_PLAN, plan.model_dump_json(indent=2))


class SupervisorRoutedPlanningExecutor:
    """AgentResult-only Planning executor for the hybrid Supervisor routing design
    (see docs/reports plan). Computes the goal specification and hands off --
    it never decides what runs next; the Supervisor + Policy Engine route to
    Fitness from here."""

    def execute(self, state: OrchestrationState, ctx: ExecutionContext | None) -> CapabilityResult:
        workspace = state["workspace_path"]
        query = state.get("fitness_query") or state["query"]
        output = build_planning_output(workspace, query)
        persist_planning_output(workspace, output)
        persist_execution_plan(workspace, build_execution_plan(workspace))
        return CapabilityResult(
            request_id=uuid4(),
            capability="planning",
            status="completed",
            summary="Goal specification complete.",
            artifacts={
                "planning_output_path": PLANNING_OUTPUT_PATH,
                "execution_plan_path": PLAN_EXECUTION_PLAN,
            },
        )


_executor: CapabilityExecutor = SupervisorRoutedPlanningExecutor()


def configure_planning_executor(executor: CapabilityExecutor | None) -> None:
    """Override the Planning capability executor (used in tests, or to swap
    in a future LLM-assisted executor)."""
    global _executor
    _executor = executor or SupervisorRoutedPlanningExecutor()


def get_planning_executor() -> CapabilityExecutor:
    return _executor
