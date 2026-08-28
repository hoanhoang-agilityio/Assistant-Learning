"""The ``summarize`` node: fold old history into a running summary once it grows too large."""

from typing import NotRequired, TypedDict

import tiktoken
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    trim_messages,
)

from src.core.llm import chat_model, with_retry_policy
from src.schemas import GraphState

SUMMARIZE_TOKEN_THRESHOLD = 6000
SUMMARIZE_KEEP_TOKENS = 3000

SUMMARIZE_SYSTEM = """
Extend the running summary of this conversation with the messages below. Keep it
factual and compact: what the user asked for, what was decided, what was done, and
anything still unresolved. Do not restate what the summary already covers unless it
still matters to what happens next.
"""

SUMMARIZE_TEMPLATE = """
<existing_summary>
{summary}
</existing_summary>

<messages_to_fold_in>
{messages}
</messages_to_fold_in>
"""

_ENCODING = tiktoken.get_encoding("cl100k_base")


class SummarizeUpdate(TypedDict):
    """The state ``summarize`` writes."""

    summary: NotRequired[str]
    messages: NotRequired[list[AnyMessage]]


def _count_tokens(messages: list[AnyMessage]) -> int:
    """Count the number of tokens in a list of messages."""

    return sum(len(_ENCODING.encode(str(message.content))) for message in messages)


def _split(messages: list[AnyMessage]) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """The old messages to fold into the summary, and the recent ones kept verbatim."""

    kept = trim_messages(
        messages,
        max_tokens=SUMMARIZE_KEEP_TOKENS,
        token_counter=_count_tokens,
        strategy="last",
        start_on="human",
    )
    return messages[: len(messages) - len(kept)], kept


def _render(messages: list[AnyMessage]) -> str:
    """Render the messages being folded in as plain transcript text."""

    return "\n".join(f"{message.type}: {message.content}" for message in messages)


async def summarize(state: GraphState) -> SummarizeUpdate:
    """Fold the oldest messages into the running summary once history grows past budget."""

    messages = state["messages"]
    if _count_tokens(messages) <= SUMMARIZE_TOKEN_THRESHOLD:
        return {}

    to_fold, _ = _split(messages)
    if not to_fold:
        return {}

    context = SUMMARIZE_TEMPLATE.format(
        summary=state.get("summary") or "none yet",
        messages=_render(to_fold),
    )

    model = with_retry_policy(chat_model())
    try:
        response = await model.ainvoke(
            [SystemMessage(content=SUMMARIZE_SYSTEM), HumanMessage(content=context)]
        )
    except Exception:
        return {}

    return {
        "summary": str(response.content),
        "messages": [RemoveMessage(id=message.id) for message in to_fold if message.id],
    }
