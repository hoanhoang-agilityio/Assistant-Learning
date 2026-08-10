"""State of the planning agent.

No ``plan`` field, and no ``draft_plan``. The agent cannot write the user's plan
because it has nowhere to write it: its only output is a ``draft_id`` minted by
``commit_draft`` (``docs/supervisor-architecture.md`` §5.1).

``preferences`` stays an extracted string rather than a transcript. The reason a
particular exercise was chosen has to be traceable to a value in state instead
of to something buried in a message list, and it means the planner cannot be
steered by anything the user said that was not first extracted deliberately.
``messages`` exists only because ``create_agent`` requires it — it holds the
agent's own tool round-trip, not the user's conversation.
"""

from typing import Any, Literal

from langchain.agents.middleware import AgentState

PlanningMode = Literal["build", "change"]


class PlanningState(AgentState):
    """Working state of the planning agent.

    ``slots`` is written by ``get_template_slots`` and read by
    ``get_exercise_candidates`` and ``commit_draft``. It carries each slot's
    legal candidate list, which is the list the model must choose from: an id
    outside it is rejected at commit time, so a contraindicated exercise cannot
    enter a plan even if the model names one.
    """

    profile: dict
    goal: str
    preferences: str

    mode: PlanningMode
    # Empty for a build. For a change, the delta the supervisor extracted —
    # `{"days": 5}` or `{"goal": "fat_loss"}`.
    changes: dict
    # The plan being changed, and the macros belonging to it. Both `None` for a
    # build. `base_macros` is here so `commit_draft` can render a diff without
    # asking the supervisor for numbers it would have to retype.
    base_plan: dict | None
    base_macros: dict | None

    template: dict | None
    slots: list[dict]
    # The handle `commit_draft` minted, and the agent's only real output. The
    # caller reads the draft back out of the store with it; nothing else the
    # agent produces is trusted, which is what stops an agent that assembled a
    # plan on its own from having produced anything the system will save.
    draft_id: str | None
    # Findings raised while setting up — a split that could not be honoured, a
    # slot with no safe exercise. They travel into the draft envelope alongside
    # the verifiers' findings, so nothing raised here is lost by the time the
    # supervisor describes the plan.
    notes: list[dict[str, Any]]
