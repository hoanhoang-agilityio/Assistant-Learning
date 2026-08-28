"""The preferences a user states about themselves: reading one turn for them, storing them.

Kept apart from the profile on purpose. A profile field is what the user *is* — an age, a
weight, a goal the plan is computed from — and the coach cannot run without it. A
preference is what they would *rather*: honoured when nothing rules it out, and never a
reason to stop and ask.
"""

from typing import Any

from src.runtime import MemoryScope
from src.services.memory import recall, recall_scope, save
from src.services.turn import PreferenceStatement

# One store entry per kind of preference, so a turn that mentions food does not rewrite
# what an earlier one said about scheduling.
SCHEDULE_KEY = "schedule"
EXERCISES_KEY = "exercises"
DIET_KEY = "diet"
RESPONSE_STYLE_KEY = "response_style"


def _texts(values: list[str]) -> list[str]:
    """Normalise a stated list: trimmed, lower-cased, no blanks, no repeats, in order."""

    seen = dict.fromkeys(
        value.strip().lower() for value in values if value and value.strip()
    )
    return list(seen)


def stated_preferences(statement: PreferenceStatement) -> dict[str, dict[str, Any]]:
    """The store entries one turn's statement asks to be written, keyed by kind."""

    entries: dict[str, dict[str, Any]] = {}

    if statement.schedule:
        entries[SCHEDULE_KEY] = {"preferred": statement.schedule.strip()}

    exercises: dict[str, Any] = {}
    if liked := _texts(statement.liked_exercises):
        exercises["liked"] = liked
    if disliked := _texts(statement.disliked_exercises):
        exercises["disliked"] = disliked
    if exercises:
        entries[EXERCISES_KEY] = exercises

    if statement.diet:
        entries[DIET_KEY] = {"preferred": statement.diet.strip()}
    if statement.response_style:
        entries[RESPONSE_STYLE_KEY] = {"preferred": statement.response_style.strip()}

    return entries


def merge_entry(stored: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Fold one turn's statement onto a stored entry.

    Lists accumulate and scalars replace, which is the difference between "I also hate
    lunges" and "actually, make it mornings": the first adds to what they have already
    said, the second corrects it.
    """

    merged = dict(stored)
    for name, value in update.items():
        if isinstance(value, list):
            merged[name] = _texts([*merged.get(name, []), *value])
        else:
            merged[name] = value
    return merged


async def load_preferences(user_id: str) -> dict[str, Any]:
    """Every preference on record for a user, keyed as it was written."""

    return await recall_scope(user_id, MemoryScope.PREFERENCES)


async def save_preferences(
    user_id: str, statement: PreferenceStatement
) -> dict[str, dict[str, Any]]:
    """Persist what this turn said the user prefers, merged onto what they said before."""

    written: dict[str, dict[str, Any]] = {}
    for key, update in stated_preferences(statement).items():
        stored = await recall(user_id, MemoryScope.PREFERENCES, key) or {}
        written[key] = await save(
            user_id, MemoryScope.PREFERENCES, key, merge_entry(stored, update)
        )
    return written


__all__ = [
    "DIET_KEY",
    "EXERCISES_KEY",
    "RESPONSE_STYLE_KEY",
    "SCHEDULE_KEY",
    "load_preferences",
    "merge_entry",
    "save_preferences",
    "stated_preferences",
]
