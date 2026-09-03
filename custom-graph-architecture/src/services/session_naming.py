"""Naming a conversation from its own content, so the sidebar has something to show.

Three steps on the first turn of an unnamed conversation: claim the row, write a
placeholder cut from the user's own message, then hand an LLM call to the background to
replace that placeholder with a real title.

The name lives in the ``session`` table, which is what ``GET /auth/sessions`` reads, so
it survives a reload, a new browser and a fresh login. Nothing here can fail a chat
turn: the claim is one statement, and every error in the background task leaves the
placeholder standing.

``_background_tasks`` is what keeps the title call alive — ``asyncio.create_task`` holds
only a weak reference, so an unheld task can be collected mid-flight and the title
silently never arrive.
"""

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from src.configs.config import settings
from src.prompts import SESSION_TITLE_SYSTEM
from src.schemas import Message, SessionTitle
from src.services.auth import auth_service
from src.services.llm import chat_model, with_retry_policy
from src.utils.logging import logger

PLACEHOLDER_MAX_CHARS = 40
TITLE_INPUT_MAX_CHARS = 1000

_background_tasks: set[asyncio.Task] = set()


def _placeholder(text: str) -> str:
    """A stand-in name cut from the message itself."""
    cleaned = " ".join(text.split())[:PLACEHOLDER_MAX_CHARS].rstrip()
    return cleaned or "New chat"


def _first_user_message(messages: list[Message]) -> str | None:
    """The text to name the conversation after, or ``None`` when the turn has none."""
    return next((item.content for item in messages if item.role == "user"), None)


async def _generate_title(text: str) -> str | None:
    """Summarise the message into a title, or ``None`` when the model cannot be reached."""
    model = with_retry_policy(
        chat_model(max_tokens=settings.SESSION_TITLE_MAX_TOKENS).with_structured_output(
            SessionTitle
        )
    )
    try:
        result = await model.ainvoke(
            [
                SystemMessage(content=SESSION_TITLE_SYSTEM),
                HumanMessage(content=text[:TITLE_INPUT_MAX_CHARS]),
            ]
        )
    except Exception:
        return None
    return str(result.title)


async def _replace_placeholder(session_id: str, text: str) -> None:
    """Overwrite the placeholder with a generated title. Never raises."""
    try:
        title = await _generate_title(text)
        if title is None:
            logger.warning("session_title_generation_failed", session_id=session_id)
            return
        await auth_service.update_session_name(session_id, title)
    except Exception:
        logger.warning("session_title_not_stored", session_id=session_id)


async def name_session(
    session_id: str, session_name: str, messages: list[Message]
) -> None:
    """Start naming a conversation, unless it already has a name or nothing to name it after.

    Awaits only the claim, which is a single round-trip. The title call runs detached, so
    the turn is never held up by it and an abandoned turn still leaves a named
    conversation behind.
    """
    if not settings.SESSION_NAMING_ENABLED or session_name:
        return

    text = _first_user_message(messages)
    if not text:
        return

    try:
        claimed = await auth_service.claim_unnamed_session(
            session_id, _placeholder(text)
        )
    except Exception:
        logger.warning("session_claim_failed", session_id=session_id)
        return
    if not claimed:
        return

    task = asyncio.create_task(_replace_placeholder(session_id, text))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


__all__ = ["PLACEHOLDER_MAX_CHARS", "TITLE_INPUT_MAX_CHARS", "name_session"]
