"""Request and response schemas for the chat endpoints."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.enums import StreamEventType

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_MESSAGE_LENGTH = 8000


class Message(BaseModel):
    """One conversation message."""

    role: Literal["user", "assistant", "system"] = Field(
        description="Who produced the message"
    )
    content: str = Field(
        min_length=1, max_length=MAX_MESSAGE_LENGTH, description="Message text"
    )

    @field_validator("content")
    @classmethod
    def strip_control_characters(cls, value: str) -> str:
        """Remove control characters before the message reaches the graph or the logs."""
        cleaned = _CONTROL_CHARS.sub("", value).strip()
        if not cleaned:
            raise ValueError("content must contain at least one printable character")
        return cleaned


class SessionTitle(BaseModel):
    """The generated name for a conversation."""

    title: str = Field(
        min_length=1,
        max_length=60,
        description="Short conversation title, in the language the user wrote in",
    )

    @field_validator("title")
    @classmethod
    def normalize(cls, value: str) -> str:
        """Collapse whitespace and drop wrapping quotes and trailing punctuation."""
        cleaned = " ".join(value.split()).strip(" \"'`.,:;!?-")
        if not cleaned:
            raise ValueError("title must contain at least one printable character")
        return cleaned


class ChatRequest(BaseModel):
    """Body of ``POST /chat`` and ``/chat/stream``."""

    messages: list[Message] = Field(
        min_length=1, description="Turn to process, newest message last"
    )
    form_data: dict[str, Any] | None = Field(
        default=None,
        description="Filled-in fields answering a form the run is suspended on",
    )


class ChatResponse(BaseModel):
    """Body of a completed chat turn."""

    messages: list[Message] = Field(
        description="Messages produced by the graph this turn"
    )
    form: dict[str, Any] | None = Field(
        default=None,
        description="Form the run is now suspended on, if it is waiting for one",
    )


class StreamResponse(BaseModel):
    """One server-sent event frame of a streamed turn.

    Four shapes behind one model: a ``step`` carries ``node`` and ``label`` and no text,
    a ``message`` carries one complete reply, a ``form`` carries the fields the run is
    waiting on, and ``done`` closes the stream. ``content`` and ``done`` keep the names
    and the meaning they had before steps existed, so a client that only reads those two
    still works.
    """

    type: StreamEventType = Field(
        default=StreamEventType.MESSAGE, description="What this frame carries"
    )
    content: str = Field(default="", description="Reply text, on a message frame")
    node: str | None = Field(
        default=None, description="Graph node reached, on a step frame"
    )
    label: str | None = Field(
        default=None, description="What to call that node in the UI"
    )
    form: dict[str, Any] | None = Field(
        default=None, description="Fields to collect, on a form frame"
    )
    done: bool = Field(
        default=False, description="True on the final frame, including errors"
    )


__all__ = [
    "MAX_MESSAGE_LENGTH",
    "ChatRequest",
    "ChatResponse",
    "Message",
    "SessionTitle",
    "StreamResponse",
]
