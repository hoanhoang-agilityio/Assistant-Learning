"""Namespace scheme for the long-term store.

A store namespace is a tuple, and a mistyped tuple does not raise — it silently addresses
an empty namespace and the caller reads back nothing. Every read and write goes through
``namespace_for`` so the three categories in the spec stay addressable by name.

Scoping is per user: ``user_id`` is the isolation boundary, so one user's accumulated
knowledge can never be retrieved for another.
"""

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
    """Build the store namespace for one user and one memory scope.

    Args:
        user_id: The user the memory belongs to.
        scope: Which of the three memory categories to address.

    Returns:
        tuple[str, str, str]: The namespace tuple to pass to the store.

    Raises:
        ValueError: If ``user_id`` is empty — an anonymous write would pool one user's
            memory into a namespace every other anonymous caller also reads.
    """
    if not user_id:
        raise ValueError("user_id is required to address long-term memory")
    return ("users", user_id, scope.value)
