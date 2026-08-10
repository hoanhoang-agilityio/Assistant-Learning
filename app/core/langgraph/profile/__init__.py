"""Profile handling: what is loaded, what is extracted, what is required.

Outside the agent registry, and now outside the root graph too. What earns a
place in ``agents/`` is an independent workflow with its own state and contract;
loading context, merging what the user just said and gating on what is missing is
orchestration the supervisor owns. After the conversion it lives in supervisor
middleware and in tool preconditions rather than in root nodes
(``docs/supervisor-architecture.md`` §12).

What stays here is the part that must be identical wherever it runs: the
controlled vocabularies and the conflict rule.
"""

from app.core.langgraph.profile.extraction import (
    ACTIVITY_LEVELS,
    EQUIPMENT_TOKENS,
    GOALS,
    SEXES,
    clean_extraction,
    goal_conflict,
    unmapped_injury_note,
)

__all__ = [
    "ACTIVITY_LEVELS",
    "EQUIPMENT_TOKENS",
    "GOALS",
    "SEXES",
    "clean_extraction",
    "goal_conflict",
    "unmapped_injury_note",
]
