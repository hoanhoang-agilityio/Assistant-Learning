"""The ``persist_preferences`` node: write what the turn said the user prefers."""

from typing import TypedDict

from src.schemas import GraphState
from src.services.preferences import save_preferences
from src.services.turn import PreferenceStatement


class PersistPreferencesUpdate(TypedDict):
    """The state ``persist_preferences`` writes — nothing; it only performs a side effect."""


async def persist_preferences(state: GraphState) -> PersistPreferencesUpdate:
    """Persist the turn's stated preferences, before the agents ask what is on record.

    Separate from ``persist_profile`` because it writes a different scope for a different
    reason: a profile field is what the coach cannot run without, a preference is what it
    should honour when nothing rules it out.
    """

    statement = PreferenceStatement.model_validate(
        (state.get("extracted_facts") or {}).get("preferences") or {}
    )
    if not statement.is_empty:
        await save_preferences(state["user_id"], statement)
    return {}
