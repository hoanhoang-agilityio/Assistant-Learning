"""Request and response schemas for the chat endpoints."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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


class ChatRequest(BaseModel):
    """Body of ``POST /chat`` and ``/chat/stream``."""

    messages: list[Message] = Field(
        min_length=1, description="Turn to process, newest message last"
    )


class ChatResponse(BaseModel):
    """Body of a completed chat turn."""

    messages: list[Message] = Field(
        description="Messages produced by the graph this turn"
    )


class StreamResponse(BaseModel):
    """One server-sent event frame of a streamed answer."""

    content: str = Field(default="", description="Incremental text chunk")
    done: bool = Field(
        default=False, description="True on the final frame, including errors"
    )


__all__ = [
    "MAX_MESSAGE_LENGTH",
    "ChatRequest",
    "ChatResponse",
    "Message",
    "StreamResponse",
]
