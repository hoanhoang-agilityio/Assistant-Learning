"""The deterministic gate: fixed rules over a finished plan, with no LLM in the loop.

Each rule is a ``PlanContext -> list[VerificationIssue]`` function in its own module, and
``RULES`` is the whole gate. Every rule runs on every plan — stopping at the first failure
would send the coach agent back for one fix at a time and burn the retry budget on a plan
that was wrong in three ways.
"""

from collections.abc import Callable

from src.schemas import TrainingPlan, UserProfile, VerificationIssue, VerificationResult
from src.verification.deterministic.availability import check_availability
from src.verification.deterministic.completeness import check_completeness
from src.verification.deterministic.context import PlanContext, build_plan_context
from src.verification.deterministic.macros import check_macros
from src.verification.deterministic.safety import check_safety
from src.verification.deterministic.volume import check_volume

Rule = Callable[[PlanContext], list[VerificationIssue]]

# Ordered as the coach agent should read them: what is missing, then what is wrong, then
# what is unsafe.
RULES: list[Rule] = [
    check_completeness,
    check_macros,
    check_volume,
    check_availability,
    check_safety,
]


def run_rules(context: PlanContext) -> VerificationResult:
    """Run every rule against a resolved plan and collect what they find."""

    return VerificationResult(
        issues=[issue for rule in RULES for issue in rule(context)]
    )


async def verify_plan(plan: TrainingPlan, profile: UserProfile) -> VerificationResult:
    """Check a plan against every deterministic rule."""

    return run_rules(await build_plan_context(plan, profile))


__all__ = [
    "RULES",
    "PlanContext",
    "Rule",
    "build_plan_context",
    "run_rules",
    "verify_plan",
]
