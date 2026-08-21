"""State of the supervisor.

Seven fields, down from twenty in the old ``RootState``. Everything that
vanished — ``draft_plan``, ``computed_macros``, ``submitted_plan``, ``issues``,
``verdict``, ``repair_count``, ``pending_commit``, ``scope``, ``changes``,
``revert_target`` — was derived *within* a turn, and derived state now lives in
the draft store instead (``docs/supervisor-architecture.md`` §4.1, §9).

What is left is exactly the set that must survive the turn boundary, which is
also why the ``NEW_TURN`` reset gets simpler rather than harder: there is very
little a turn writes that the next turn must not see.
"""

from typing import Any

from langchain.agents.middleware import AgentState

from app.schemas.graph import GoalConflict


class SupervisorState(AgentState):
    """Working state of the supervisor.

    ``messages`` comes from ``AgentState``, along with the private keys the
    agent runtime needs.
    """

    profile: dict
    # What the user *has*. Survives the turn: it is rehydrated from the newest
    # saved version when a session starts without one, and overwritten only by
    # `save_plan`.
    plan: dict | None
    macros: dict | None
    episodic_context: str
    # Parent of the next snapshot, so the version history is a chain rather than
    # a pile.
    current_version_id: str | None

    missing_fields: list[str]
    goal_conflict: GoalConflict | None


# Written by the topic gate, which runs once at the start of every turn, so each
# turn starts from the same blank working set no matter what ran before it.
#
# Short, and that is the point. Under the old root graph this reset had to clear
# nine derived fields, because the checkpointer kept a build's findings and draft
# alive into the change request that followed. Derived state now lives in the
# draft store keyed by a handle, so there is nothing left to clear but the two
# questions a turn asks.
#
# Short is not the same as unnecessary. `missing_fields` is written by a tool
# refusal and by nothing else — `_refuse` omits the key entirely when nothing is
# missing, so this reset is the only thing that ever clears it. Without it the
# turn *after* the user supplies a field is still told to ask for it.
#
# What is deliberately absent is as important. `plan`, `macros`, `profile` and
# `current_version_id` are what the user has; they are meant to survive, and
# clearing them here would delete the plan every turn.
NEW_TURN: dict[str, Any] = {
    "missing_fields": [],
    # Derived from this turn's wording, so it must not outlive it. `extract_profile`
    # overwrites it every turn it runs, which makes this redundant on the happy
    # path and load-bearing on the one that matters: the extractor returns early
    # when it fails, and a stale conflict re-asks a question already resolved.
    "goal_conflict": None,
}


__all__ = ["NEW_TURN", "SupervisorState"]
