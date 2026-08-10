"""Compute macros for a plan and score it against the rubrics — together.

One function, called from every tool body that produces or assesses a plan. That
is not tidiness; it is the replacement for a guarantee the old root graph got
from its topology (``docs/supervisor-architecture.md`` §11.1). There, no path
from a plan to an answer could skip ``calc_macro`` because ``calc_macro`` was the
only edge into ``verification``. Here the two are bundled into one call, so a
tool that scores a plan without computing its macros would have to go out of its
way to do so — and the test suite asserts that none does.

The verification graph is invoked with no messages, and ``VerifyState`` has no
field to put them in. In this architecture that guarantee is stronger than it was
as a node: this is a plain function that is never handed a transcript, so there
is nothing to pass in even by mistake.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.langgraph.agents.verification import get_verification_graph
from app.core.logging import logger
from app.schemas.graph import Issue, Verdict, VerifyScope
from app.services.catalog import load_catalog
from app.services.nutrition import calc_macros
from app.services.rubrics import rubric_version

_DEFAULT_GOAL = "general_health"


def sessions_for(plan: dict[str, Any], profile: dict[str, Any]) -> int:
    """Count the sessions a week this plan actually trains.

    Counted off the plan rather than read from the profile, because the profile
    holds what was *asked for*: a slot with no legal exercise leaves a day out,
    and the count that feeds TDEE has to be the one the user will train.

    Args:
        plan: The plan being assessed.
        profile: The user's profile, used only when the plan has no days.

    Returns:
        Sessions per week.
    """
    return len(plan.get("days") or []) or int(profile.get("days_per_week") or 3)


async def score(
    plan: dict[str, Any],
    profile: dict[str, Any],
    config: RunnableConfig | None = None,
    scope: list[VerifyScope] | None = None,
) -> tuple[dict[str, Any], list[Issue], Verdict]:
    """Compute this plan's macros and run the enabled rubric checks over both.

    Args:
        plan: The plan to score.
        profile: The user's profile. Every required field is present by the time
            this runs — the profile precondition on the calling tool saw to that.
        config: Runnable config, forwarded so the verification spans nest under
            the current trace.
        scope: Which verifiers to run. ``None`` or empty means all three, which
            is mandatory for anything that could be saved; only a read-only
            review lets the user's wording narrow it.

    Returns:
        ``(macros, issues, verdict)``. ``macros`` is never empty, which is the
        invariant every draft envelope depends on.

    Raises:
        KeyError: When a required profile field is absent, which means a tool
            ran its body without its precondition passing.
    """
    macros = calc_macros(
        profile,
        sessions_per_week=sessions_for(plan, profile),
        goal=profile.get("goal", _DEFAULT_GOAL),
    )

    result = await get_verification_graph().ainvoke(
        {
            "plan": plan,
            "profile": profile,
            "computed_macros": macros,
            "catalog": load_catalog(),
            "scope": scope or [],
            "rubric_version": rubric_version(),
            "issues": [],
            "verdict": None,
        },
        config or {},
    )

    issues: list[Issue] = result["issues"]
    verdict: Verdict = result["verdict"]
    logger.info(
        "plan_scored", verdict=verdict, issues=len(issues), sessions=len(plan.get("days") or [])
    )
    return macros, issues, verdict


__all__ = ["score", "sessions_for"]
