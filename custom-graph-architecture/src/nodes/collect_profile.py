"""The ``collect_profile`` node: ask for every missing profile field in one form, and save them together."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.types import interrupt

from src.schemas import GraphState, ProfileStatus
from src.services.profile import save_profile
from src.services.profile_form import (
    ProfileFormField,
    profile_form_fields,
    submitted_values,
    validate_profile_submission,
)

PROFILE_FORM_INTERRUPT = "profile_form"

PROFILE_FORM_ASK = (
    "Before I can build you a plan I need a few details about you. I've filled in what "
    "you've already told me — check those over and complete the rest."
)

PROFILE_SAVED_MESSAGE = (
    "Thanks — I've got everything I need. Let me put your plan together."
)


class ProfileFormInterrupt(TypedDict):
    """The form the caller is shown while the run is suspended here."""

    type: str
    summary: str
    fields: list[ProfileFormField]
    values: dict
    errors: dict[str, str]


class CollectProfileUpdate(TypedDict):
    """The state ``collect_profile`` writes once the form comes back complete."""

    profile: dict
    profile_draft: None
    profile_status: ProfileStatus
    messages: list[AnyMessage]


async def collect_profile(state: GraphState) -> CollectProfileUpdate:
    """Ask for every profile field the coach is missing in one form, and save them once they all validate."""

    profile = state.get("profile")
    fields = profile_form_fields(profile, state.get("profile_draft"))
    values = dict(state.get("profile_draft") or {})
    errors: dict[str, str] = {}

    while True:
        reply = interrupt(
            ProfileFormInterrupt(
                type=PROFILE_FORM_INTERRUPT,
                summary=PROFILE_FORM_ASK,
                fields=fields,
                values=values,
                errors=errors,
            )
        )
        values = submitted_values(reply)
        validated, errors = validate_profile_submission(profile, values)
        if not errors:
            break

    saved = await save_profile(state["user_id"], validated)

    return {
        "profile": saved,
        "profile_draft": None,
        "profile_status": "ready",
        "messages": [AIMessage(content=PROFILE_SAVED_MESSAGE)],
    }
