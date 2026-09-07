"""Namespace scheme for the long-term store."""

from enum import StrEnum


class MemoryScope(StrEnum):
    """The kinds of long-term user memory that have a writer.

    The spec named three. ``PREFERENCES`` and ``KNOWLEDGE`` were removed once the
    supervisor migration deleted the node that wrote them: an addressable scope nothing
    fills reads as working memory right up until every lookup comes back empty.

    Attributes:
        FACTS: Name, age, weight, sex, activity level, goal, equipment, injuries.
    """

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
