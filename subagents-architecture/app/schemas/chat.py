"""Request and response schemas for the chatbot endpoints."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import StructuredOutput

# Control characters are stripped rather than rejected: they carry no meaning in
# chat text and a paste from a terminal or PDF routinely contains them.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_MESSAGE_LENGTH = 8000


class Message(BaseModel):
    """One conversation message."""

    role: Literal["user", "assistant", "system"] = Field(description="Who produced the message")
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH, description="Message text")

    @field_validator("content")
    @classmethod
    def strip_control_characters(cls, value: str) -> str:
        """Remove control characters that would corrupt logs and the trace view."""
        cleaned = _CONTROL_CHARS.sub("", value).strip()
        if not cleaned:
            raise ValueError("content must contain at least one printable character")
        return cleaned


class ChatRequest(BaseModel):
    """Body of ``POST /chatbot/chat`` and ``/chatbot/chat/stream``."""

    messages: list[Message] = Field(
        min_length=1, description="Turn to process, newest message last"
    )


class ChatResponse(BaseModel):
    """Body of a completed chat turn."""

    messages: list[Message] = Field(description="Messages produced by the agent this turn")


class StreamResponse(BaseModel):
    """One server-sent event frame of a streamed answer."""

    content: str = Field(default="", description="Incremental text chunk")
    done: bool = Field(default=False, description="True on the final frame, including errors")


class SessionTitle(StructuredOutput):
    """Structured output schema for auto-generated session titles.

    The bound and the validator are the guardrail around a model asked for a
    bare title: wrapping quotes and trailing punctuation are stripped here
    rather than in the sidebar, and anything longer than a title is rejected
    outright. Prefixes like ``Title:`` are the prompt's job, not the schema's.
    """

    title: str = Field(
        min_length=1,
        max_length=60,
        description="Short conversation title in the user's language",
    )

    @field_validator("title")
    @classmethod
    def _normalize(cls, v: str) -> str:
        """Collapse whitespace and strip surrounding quotes and punctuation."""
        v = " ".join(v.split()).strip(" \"'`.,:;!?-")
        if not v:
            raise ValueError("empty title after normalization")
        return v


class SessionSummary(StructuredOutput):
    """Structured output schema for an episodic session summary.

    ``max_length`` is the real guardrail, not formatting. This text is carried
    into the system prompt on every subsequent turn, so a model that decides to
    recap the whole conversation would push the actual request out of the way
    and hand the answer a second, competing account of the user's plan.
    """

    summary: str = Field(
        min_length=1,
        max_length=400,
        description="Two or three sentences on what happened in this conversation",
    )

    @field_validator("summary")
    @classmethod
    def _normalize(cls, v: str) -> str:
        """Collapse whitespace and strip surrounding quotes."""
        v = " ".join(v.split()).strip(" \"'`")
        if not v:
            raise ValueError("empty summary after normalization")
        return v
