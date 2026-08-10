"""Message helpers shared by every agent package."""

from langchain_core.messages import AIMessage, BaseMessage

from app.schemas.chat import Message

# Roles LangChain will not accept back as input. Tool results are replayed from
# the checkpoint by the framework itself, so dropping them here is correct.
_EXPORTABLE_ROLES = {"user", "assistant", "system"}


def dump_messages(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to the dicts the LLM service expects.

    Args:
        messages: Messages to convert.

    Returns:
        One ``{"role": ..., "content": ...}`` dict per message.
    """
    return [{"role": _role_of(message), "content": message_text(message)} for message in messages]


def to_chat_messages(messages: list[BaseMessage]) -> list[Message]:
    """Convert graph messages into the API's response schema.

    Messages whose role has no API equivalent (tool results, tool-call-only
    assistant turns) are dropped rather than rendered as empty bubbles.

    Args:
        messages: Messages read from graph state.

    Returns:
        Messages safe to serialise in a ``ChatResponse``.
    """
    result: list[Message] = []
    for message in messages:
        role = _role_of(message)
        content = message_text(message)
        if role in _EXPORTABLE_ROLES and content:
            result.append(Message(role=role, content=content))
    return result


def _role_of(message: BaseMessage) -> str:
    """Map a LangChain message type to a chat role."""
    if isinstance(message, AIMessage):
        return "assistant"
    return {"human": "user", "ai": "assistant", "system": "system"}.get(message.type, message.type)


def message_text(message: BaseMessage) -> str:
    """Extract plain text from a model response.

    **Always use this instead of reading ``.content`` directly.** A reasoning
    model returns a *list* of content blocks — ``['reasoning', 'text']`` — not a
    string, so ``content if isinstance(content, str) else ""`` silently yields
    an empty answer. Nothing raises, the turn succeeds, and the user gets
    nothing back.

    Args:
        message: The response to read.

    Returns:
        The concatenated text blocks, or the content itself when it is already
        a plain string.
    """
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


__all__ = ["dump_messages", "message_text", "to_chat_messages"]
