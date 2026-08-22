"""Namespace scheme for the long-term store."""

from enum import StrEnum


class MemoryScope(StrEnum):
    """The three kinds of long-term user memory named in the spec.

    Attributes:
        PREFERENCES: Preferred workout schedule, favourite exercises, dietary preferences,
            preferred response style.
        KNOWLEDGE: Behavioural patterns learned over time, e.g. skips workouts longer than
            60 minutes, adheres better to 4-day plans.
        FACTS: Name, age, weight, sex, activity level, goal, equipment, injuries.
    """

    PREFERENCES = "preferences"
    KNOWLEDGE = "knowledge"
    FACTS = "facts"


def namespace_for(user_id: str, scope: MemoryScope) -> tuple[str, str, str]:
    """Build the store namespace for one user and one memory scope."""

    if not user_id:
        raise ValueError("user_id is required to address long-term memory")
    return ("users", user_id, scope.value)


def plan_namespace(user_id: str) -> tuple[str, str, str]:
    """Build the store namespace holding one user's training plan."""

    if not user_id:
        raise ValueError("user_id is required to address a stored plan")
    return ("users", user_id, "plan")
