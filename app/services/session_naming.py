"""Session auto-naming.

On the first turn of an unnamed session this module:
  1. Atomically claims the session in Postgres, so concurrent requests and
     multiple uvicorn workers cannot each fire an LLM call for the same row.
  2. Writes a placeholder derived from the user's message, so the session has a
     usable name immediately and keeps one even if the LLM call later fails.
  3. Fires a background task that asks a nano model for a proper title with
     structured output and overwrites the placeholder.

Naming never blocks and never fails a chat turn: the claim is one round-trip and
every error in the background task degrades to the placeholder.

The call goes through ``llm_service`` directly rather than the graph, so it
carries no Langfuse callbacks and produces no trace. That is deliberate for a
32-token nano call — a second ``CallbackHandler`` built here would only duplicate
spans on the root graph's traces.
"""

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import Session as DBSession
from sqlmodel import col, update

from app.core.logging import logger
from app.core.prompts import SESSION_TITLE_PROMPT
from app.models.session import Session as ChatSession
from app.schemas.chat import SessionTitle
from app.services.database import database_service
from app.services.llm import llm_service

_PLACEHOLDER_MAX = 40
_PROMPT_INPUT_MAX = 500

# create_task only holds a weak reference; without this set a title can vanish
# mid-flight when the collector runs.
_background_tasks: set[asyncio.Task] = set()


def _build_placeholder(user_message: str) -> str:
    """Collapse whitespace and truncate the message into a stand-in name.

    Args:
        user_message: The first user message of the session.

    Returns:
        The placeholder name, never empty.
    """
    cleaned = " ".join(user_message.split())
    return cleaned[:_PLACEHOLDER_MAX].rstrip() or "New chat"


def _claim_session(session_id: str, placeholder: str) -> bool:
    """Claim an unnamed session and write the placeholder in one statement.

    The claim and the placeholder write are the same ``UPDATE`` on purpose.
    Splitting them into a ``SELECT`` then an ``UPDATE`` reopens the race this
    exists to close.

    Args:
        session_id: The session to claim.
        placeholder: The stand-in name written by the winning claim.

    Returns:
        True only for the caller whose ``UPDATE`` matched the row. Everyone else
        lost the race and must not fire an LLM call.
    """
    with DBSession(database_service.engine) as db:
        statement = (
            update(ChatSession)
            .where(col(ChatSession.id) == session_id, col(ChatSession.name) == "")
            .values(name=placeholder)
        )
        result = db.exec(statement)
        db.commit()
        return (result.rowcount or 0) == 1


async def _persist_session_name(session_id: str, user_message: str) -> None:
    """Generate a title and overwrite the placeholder. Never raises.

    Args:
        session_id: The claimed session.
        user_message: The first user message, truncated before it is sent.
    """
    try:
        result = await llm_service.call(
            [
                SystemMessage(content=SESSION_TITLE_PROMPT),
                HumanMessage(content=user_message[:_PROMPT_INPUT_MAX]),
            ],
            model_name="gpt-5.4-nano",
            response_format=SessionTitle,
            reasoning={"effort": "low"},
            max_tokens=32,
            temperature=0.3,
        )
        await database_service.update_session_name(session_id, result.title)
        logger.info("session_name_generated", session_id=session_id, name=result.title)
    except Exception:
        # The placeholder stays. A failed title is not a failed conversation.
        logger.exception("session_name_generation_failed", session_id=session_id)


def maybe_name_session(session_id: str, session_name: str, messages: list) -> None:
    """Start auto-naming if the session is still unnamed.

    Synchronous by design: it opens one short database session and returns, so a
    caller cannot accidentally await the naming. Safe to call from any chat
    endpoint on every turn — named sessions return on the first guard, and
    concurrent callers for the same session are deduplicated by the claim.

    Args:
        session_id: The session being chatted in.
        session_name: Its current name. An empty string means unnamed.
        messages: This turn's request messages.
    """
    if session_name:
        return
    first_user_msg = next((m.content for m in messages if m.role == "user"), None)
    if not first_user_msg:
        return
    if _claim_session(session_id, _build_placeholder(first_user_msg)):
        task = asyncio.create_task(_persist_session_name(session_id, first_user_msg))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
