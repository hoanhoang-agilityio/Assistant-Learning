"""Deterministic execution plan templates for common goal archetypes."""

from collections.abc import Callable
from typing import Any

from core.subgraphs.planning.schema import ExecutionPlan, PlanTask


def _task(order: int, task: str, rationale: str) -> PlanTask:
    return PlanTask(order=order, task=task, rationale=rationale)


_TEMPLATES: dict[str, Callable[[dict[str, Any]], ExecutionPlan]] = {}


def _register(template_id: str):
    def decorator(builder):
        _TEMPLATES[template_id] = builder
        return builder

    return decorator


@_register("fat_loss_moderate")
def _fat_loss_moderate(profile: dict[str, Any]) -> ExecutionPlan:
    horizon = profile.get("horizon_weeks")
    horizon_text = f" over {horizon} weeks" if horizon else ""
    return ExecutionPlan(
        template_id="fat_loss_moderate",
        plan_rationale=(
            f"Evidence plan for moderate fat loss{horizon_text} with safe deficit, "
            "training volume, and source verification."
        ),
        tasks=[
            _task(
                1,
                "Research safe fat-loss rates and caloric deficit limits for the user's profile",
                "Establish a safe weight-loss pace before prescribing nutrition changes.",
            ),
            _task(
                2,
                "Gather resistance-training volume guidance to preserve lean mass during fat loss",
                "Support workout design with evidence on maintaining muscle during a deficit.",
            ),
            _task(
                3,
                "Verify credibility of nutrition and training sources for fat-loss planning",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: fat_loss\n"
            f"- Archetype: fat_loss_moderate\n"
            f"- Horizon weeks: {horizon or 'unspecified'}\n"
            f"- Tasks: safe deficit, lean-mass preservation, source verification\n"
        ),
    )


@_register("fat_loss_aggressive_review_required")
def _fat_loss_aggressive(profile: dict[str, Any]) -> ExecutionPlan:
    horizon = profile.get("horizon_weeks")
    return ExecutionPlan(
        template_id="fat_loss_aggressive_review_required",
        plan_rationale=(
            "Evidence plan for an aggressive fat-loss target requiring safety review, "
            "feasibility analysis, and recovery considerations."
        ),
        tasks=[
            _task(
                1,
                "Research health risks and safe upper limits for rapid weight loss",
                "Assess whether the requested timeline is medically reasonable.",
            ),
            _task(
                2,
                "Gather evidence on minimum calorie floors, protein needs, and recovery during aggressive cuts",
                "Support safer prescription boundaries for nutrition and training.",
            ),
            _task(
                3,
                "Verify credibility of safety-focused fat-loss and recovery sources",
                "Ensure downstream synthesis uses trustworthy safety evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: fat_loss\n"
            f"- Archetype: fat_loss_aggressive_review_required\n"
            f"- Horizon weeks: {horizon or 'unspecified'}\n"
            f"- Tasks: safety limits, recovery guidance, source verification\n"
        ),
    )


@_register("muscle_gain_lean_bulk")
def _muscle_gain(profile: dict[str, Any]) -> ExecutionPlan:
    horizon = profile.get("horizon_weeks")
    return ExecutionPlan(
        template_id="muscle_gain_lean_bulk",
        plan_rationale=(
            "Evidence plan for lean muscle gain with sustainable surplus, hypertrophy volume, "
            "and progressive overload guidance."
        ),
        tasks=[
            _task(
                1,
                "Research sustainable lean-bulk rates and calorie surplus recommendations",
                "Match nutrition evidence to the user's muscle-gain timeline.",
            ),
            _task(
                2,
                "Gather hypertrophy volume and progressive overload guidance for the user's training frequency",
                "Support workout design with evidence-based volume prescriptions.",
            ),
            _task(
                3,
                "Verify credibility of hypertrophy and nutrition sources for muscle gain",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: muscle_gain\n"
            f"- Archetype: muscle_gain_lean_bulk\n"
            f"- Horizon weeks: {horizon or 'unspecified'}\n"
            f"- Tasks: lean bulk, hypertrophy volume, source verification\n"
        ),
    )


@_register("recomposition")
def _recomposition(profile: dict[str, Any]) -> ExecutionPlan:
    horizon = profile.get("horizon_weeks", 12)
    return ExecutionPlan(
        template_id="recomposition",
        plan_rationale=(
            "Evidence plan for body recomposition with high protein intake, resistance training "
            "priority, and modest caloric strategy."
        ),
        tasks=[
            _task(
                1,
                "Research body recomposition protocols for concurrent fat loss and muscle retention",
                "Establish evidence for dual-track nutrition and training priorities.",
            ),
            _task(
                2,
                "Gather hypertrophy and protein-intake evidence for recomposition training blocks",
                "Support workout and macro design for recomposition goals.",
            ),
            _task(
                3,
                "Verify credibility of recomposition and hypertrophy sources",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: recomposition\n"
            f"- Archetype: recomposition\n"
            f"- Horizon weeks: {horizon}\n"
            f"- Tasks: recomp protocols, protein/hypertrophy, source verification\n"
        ),
    )


@_register("strength_focus")
def _strength_focus(profile: dict[str, Any]) -> ExecutionPlan:
    del profile
    return ExecutionPlan(
        template_id="strength_focus",
        plan_rationale="Evidence plan for strength development with periodization and recovery guidance.",
        tasks=[
            _task(
                1,
                "Research evidence-based strength programming and periodization principles",
                "Establish foundational strength-training evidence.",
            ),
            _task(
                2,
                "Gather recovery and nutrition guidance for strength-focused training",
                "Support macro and recovery decisions with credible sources.",
            ),
            _task(
                3,
                "Verify credibility of strength-training sources",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            "# Planning Summary\n\n"
            "- Goal: strength\n"
            "- Archetype: strength_focus\n"
            "- Tasks: periodization, recovery, source verification\n"
        ),
    )


@_register("endurance_timeline_bound")
def _endurance(profile: dict[str, Any]) -> ExecutionPlan:
    horizon = profile.get("horizon_weeks")
    return ExecutionPlan(
        template_id="endurance_timeline_bound",
        plan_rationale=(
            f"Evidence plan for endurance development{f' over {horizon} weeks' if horizon else ''} "
            "with progressive conditioning and recovery guidance."
        ),
        tasks=[
            _task(
                1,
                "Research progressive endurance training principles for the user's timeline",
                "Establish conditioning evidence aligned with the stated horizon.",
            ),
            _task(
                2,
                "Gather recovery and fueling guidance for endurance training blocks",
                "Support nutrition and recovery decisions with credible sources.",
            ),
            _task(
                3,
                "Verify credibility of endurance-training sources",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: endurance\n"
            f"- Archetype: endurance_timeline_bound\n"
            f"- Horizon weeks: {horizon or 'unspecified'}\n"
            f"- Tasks: conditioning progression, recovery, source verification\n"
        ),
    )


@_register("maintenance")
def _maintenance(profile: dict[str, Any]) -> ExecutionPlan:
    del profile
    return ExecutionPlan(
        template_id="maintenance",
        plan_rationale="Evidence plan for maintenance-focused training and nutrition stability.",
        tasks=[
            _task(
                1,
                "Research maintenance-calorie and training-volume guidance for long-term adherence",
                "Establish evidence for sustainable maintenance programming.",
            ),
            _task(
                2,
                "Gather balanced training guidance for health and performance maintenance",
                "Support workout design with credible maintenance evidence.",
            ),
            _task(
                3,
                "Verify credibility of maintenance-focused fitness sources",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            "# Planning Summary\n\n"
            "- Goal: maintenance\n"
            "- Archetype: maintenance\n"
            "- Tasks: maintenance calories, balanced training, source verification\n"
        ),
    )


@_register("general_fitness")
def _general_fitness(profile: dict[str, Any]) -> ExecutionPlan:
    goal = profile.get("goal", "general_fitness")
    return ExecutionPlan(
        template_id="general_fitness",
        plan_rationale=(
            f"Research plan tailored for {goal} with evidence gathering and source verification."
        ),
        tasks=[
            _task(
                1,
                f"Research evidence-based training principles for {goal}",
                f"Establish foundational evidence for the user's {goal} goal.",
            ),
            _task(
                2,
                "Gather activity-level training volume recommendations",
                "Match training frequency to the user's current activity level.",
            ),
            _task(
                3,
                "Verify fitness-domain credibility of selected sources",
                "Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: {goal}\n"
            f"- Archetype: general_fitness\n"
            f"- Tasks: foundational evidence, volume guidance, source verification\n"
        ),
    )


def build_template_execution_plan(profile: dict[str, Any]) -> ExecutionPlan | None:
    """Return a deterministic execution plan for a known goal archetype."""
    archetype = str(profile.get("goal_archetype", "general_fitness"))
    builder = _TEMPLATES.get(archetype)
    if builder is None:
        return None
    return builder(profile)


def list_template_ids() -> list[str]:
    return sorted(_TEMPLATES.keys())
