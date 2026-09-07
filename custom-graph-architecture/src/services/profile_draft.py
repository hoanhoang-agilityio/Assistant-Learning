"""Reading back the profile fields a user has already stated, to pre-fill the form."""

from typing import Any

from langchain_core.messages import AnyMessage, SystemMessage
from pydantic import BaseModel, Field, create_model

from src.prompts import PROFILE_DRAFT_SYSTEM
from src.schemas import UserProfile
from src.services.llm import chat_model, with_retry_policy
from src.services.profile_form import FORM_FIELDS

# Every form field, made optional: the same fields the form asks for, so a draft can
# fill any of them, and none of them can be demanded of a conversation that never
# mentioned it.
ProfileDraft: type[BaseModel] = create_model(
    "ProfileDraft",
    **{
        name: (
            UserProfile.model_fields[name].annotation | None,
            Field(default=None, description=UserProfile.model_fields[name].description),
        )
        for name in FORM_FIELDS
    },
)
ProfileDraft.__doc__ = "The profile fields a conversation states, each unset unless it was actually stated."


async def draft_profile(messages: list[AnyMessage]) -> dict[str, Any]:
    """The profile fields the conversation already states, or nothing when none can be read."""

    model = with_retry_policy(chat_model().with_structured_output(ProfileDraft))

    try:
        draft = await model.ainvoke(
            [SystemMessage(content=PROFILE_DRAFT_SYSTEM), *messages]
        )
    except Exception:
        return {}

    return draft.model_dump(mode="json", exclude_none=True)


__all__ = ["ProfileDraft", "draft_profile"]
