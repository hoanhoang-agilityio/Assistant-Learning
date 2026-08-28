"""Trimming of the conversation history handed to the coach and QA agents."""

import tiktoken
from langchain_core.messages import AnyMessage, trim_messages

from src.configs.config import settings

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _count_tokens(messages: list[AnyMessage]) -> int:
    """Count the number of tokens in a list of messages."""

    return sum(len(_ENCODING.encode(str(message.content))) for message in messages)


def trim_history(messages: list[AnyMessage]) -> list[AnyMessage]:
    """The most recent turns that fit the shared history budget, cut on a human boundary."""

    return trim_messages(
        messages,
        max_tokens=settings.HISTORY_MAX_TOKENS,
        token_counter=_count_tokens,
        strategy="last",
        start_on="human",
    )
