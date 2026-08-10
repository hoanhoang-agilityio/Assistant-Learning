"""Tools owned by the QA agent.

``estimate_macros`` is safe here and **only** here
(``docs/supervisor-architecture.md`` §7). QA is read-only and has no path to a
save, so a number produced for a what-if question cannot leak into a stored plan.
Giving the same tool to the planning agent would put a second, unverified macro
calculation next to the one ``commit_draft`` runs, and two different numbers for
the same question are worse than one general answer.
"""

import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from app.core.logging import logger
from app.services.nutrition import calc_macros

# What a what-if defaults to when the user did not say. Sessions come from the
# profile because "what would 5 days do" only means something against the number
# they train now.
_DEFAULT_SESSIONS = 3


@tool
def estimate_macros(
    runtime: ToolRuntime,
    sessions_per_week: int | None = None,
    weight_kg: float | None = None,
    goal: str | None = None,
) -> str:
    """Estimate nutrition targets for a hypothetical change.

    Use this **only** for what-if questions — "what would 5 days a week do to my
    calories?", "what if I were aiming for fat loss instead?". Every argument you
    leave out is taken from the user's stored profile, so pass only what the
    question changes.

    Do **not** use this to answer what the user's current targets are. Those are
    in the plan section of your prompt and must be quoted from there verbatim.
    Two different numbers for the same question are worse than one.

    Args:
        runtime: Tool runtime, read for the user's profile in state.
        sessions_per_week: Sessions to assume instead of their current count.
        weight_kg: Body weight to assume instead of their stored one.
        goal: ``fat_loss``, ``muscle_gain``, ``recomp`` or ``general_health`` to
            assume instead of their stored goal.

    Returns:
        The estimated targets as JSON, labelled as an estimate. An explanation of
        what is missing when the profile does not carry enough to compute one.
    """
    profile = dict(runtime.state.get("profile") or {})
    if weight_kg is not None:
        profile["weight_kg"] = weight_kg

    assumed_goal = goal or profile.get("goal") or "general_health"
    sessions = sessions_per_week or profile.get("days_per_week") or _DEFAULT_SESSIONS

    try:
        macros = calc_macros(profile, sessions_per_week=int(sessions), goal=assumed_goal)
    except (KeyError, ValueError) as e:
        # A missing field is an ordinary outcome here, not a failure: QA has no
        # profile gate in front of it by design, so the honest answer is the
        # general form plus a request for the number.
        logger.info("qa_estimate_macros_incomplete_profile", error=str(e))
        return (
            "Not enough is known to estimate this. Answer in the general per-kg form "
            f"and ask for what is missing ({e})."
        )

    logger.info("qa_estimate_macros", sessions=sessions, goal=assumed_goal)
    return json.dumps(
        {
            "estimate": True,
            "note": (
                "A hypothetical, not the user's current targets. Present it as an estimate "
                "and name the assumptions below."
            ),
            "assumptions": {
                "sessions_per_week": int(sessions),
                "weight_kg": profile.get("weight_kg"),
                "goal": assumed_goal,
            },
            "macros": macros,
        },
        ensure_ascii=False,
    )


__all__ = ["estimate_macros"]
