"""Prompts owned by the planning agent, read once at import."""

import json
from pathlib import Path
from typing import Any

_PROMPTS_DIR = Path(__file__).parent

_PLANNING_AGENT_TEMPLATE = (_PROMPTS_DIR / "planning_agent.md").read_text(encoding="utf-8")

_NO_PREFERENCES = "The user has not stated any exercise preferences."

_BUILD_GUIDANCE = (
    "There is no existing plan. Every slot is yours to fill, and variety across "
    "the week is worth more here than anywhere else."
)

# What "change" means, spelled out, because the failure it guards against is a
# plausible one: the slots already carry the exercises the user has been happy
# with, and a model that treats a change request as a fresh build will replace
# all of them while producing a perfectly valid plan.
_CHANGE_GUIDANCE = (
    "The user already has a plan and asked for a change. The slots below already "
    "carry the change: each one shows `current_exercise_id`, the exercise the "
    "plan uses today. Keep those unless a verification finding names them. "
    "Committing with no choices at all keeps every current exercise, which is "
    "usually the right first move.\n\nWhat they asked to change: {changes}"
)


def load_planning_agent_prompt(
    mode: str, profile: str, preferences: str = "", changes: dict[str, Any] | None = None
) -> str:
    """Render the planning agent's system prompt.

    Args:
        mode: ``"build"`` or ``"change"``.
        profile: The user's standing facts, rendered as text.
        preferences: Free-text preferences extracted from the conversation.
        changes: The delta being applied, for a change.

    Returns:
        The formatted prompt.
    """
    guidance = (
        _CHANGE_GUIDANCE.format(changes=json.dumps(changes or {}, ensure_ascii=False))
        if mode == "change"
        else _BUILD_GUIDANCE
    )
    return _PLANNING_AGENT_TEMPLATE.format(
        mode=mode,
        mode_guidance=guidance,
        profile=profile or "Nothing recorded about this user yet.",
        preferences=preferences or _NO_PREFERENCES,
    )


__all__ = ["load_planning_agent_prompt"]
