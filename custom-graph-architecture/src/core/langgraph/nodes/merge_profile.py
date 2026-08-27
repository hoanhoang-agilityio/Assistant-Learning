"""The ``merge_profile`` node: fold the turn's stated facts into the runtime profile."""

from typing import TypedDict

from src.schemas import GraphState
from src.services.profile import merge_profile_updates, pending_revision_fields
from src.services.turn import ProfileStatement


class MergeProfileUpdate(TypedDict):
    """The state ``merge_profile`` writes — the only node that rewrites ``profile``."""

    profile: dict | None
    revision_fields: list[str]


async def merge_profile(state: GraphState) -> MergeProfileUpdate:
    """Merge this turn's stated fields and injuries onto the profile loaded from the store."""

    statement = ProfileStatement.model_validate(state.get("extracted_facts") or {})

    merged = merge_profile_updates(state.get("profile"), statement)
    revision_fields = pending_revision_fields(
        merged, [*state.get("revision_fields", []), *statement.fields_to_revise]
    )

    return {"profile": merged, "revision_fields": revision_fields}
