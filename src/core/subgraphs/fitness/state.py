from typing import TypedDict


class FitnessState(TypedDict):
    """Scoped state for the Fitness subgraph."""

    macro_targets: dict
    training_constraints: dict
    training_plan: dict | None
    draft_plan: str | None
    safety_flags: list[str]
