"""State of the review agent.

Carries ``messages`` because the plan being reviewed *is* what the user typed:
reading the conversation is the job here, unlike in the verifier.

What it does **not** carry is a field any of this could be written back into.
There is no ``plan``, no ``draft_plan`` and no ``draft_id`` — the plan someone
pasted to ask an opinion about must not become the plan they follow, and under
the supervisor architecture that is enforced by the absence of a handle rather
than by two separate state fields (``docs/supervisor-architecture.md`` §6.2).
"""

from langchain.agents.middleware import AgentState

from app.schemas.graph import PastedDay


class ReviewState(AgentState):
    """Working state of the review agent."""

    catalog: dict
    profile: dict

    submitted: list[PastedDay]

    # The plan as it was understood, kept so the caller can report *what* was
    # assessed. Not a handle, and nothing accepts it as one.
    submitted_plan: dict | None
    # Lines no catalog entry matched confidently, each with the candidates that
    # were considered. Reported, never guessed.
    unresolved: list[dict]
    # Lines missing sets or reps: the volume check has nothing to count for them.
    incomplete: list[str]
    # Set by `score_plan` once there is something to report.
    scored: bool
