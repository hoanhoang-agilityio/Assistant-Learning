"""Turn a fetched Langfuse item into the inputs an evaluator is given.

``item`` is keyword-only. The SDK's own docstring shows ``def mapper(trace):``,
which does not satisfy the ``MapperFunction`` Protocol it is documenting —
``__call__(self, *, item, **kwargs)``. Passing it positionally raises.

Nothing here may raise on a malformed item: the mapper runs once per fetched
trace, and one bad shape must not end the run. Missing pieces come back as empty
strings, which the evaluators treat as "abstain".
"""

import ast
import asyncio
import json
from functools import lru_cache
from typing import Any

from langfuse import EvaluatorInputs, Langfuse

from app.core.logging import logger
from evals.client import build_client

TOOL_CONTENT_LIMIT = 300

# The parent trace is fetched for its last message only, so there is no reason
# to pull observations, scores or metrics back with it.
PARENT_TRACE_FIELDS = "core,io"

_read_client: Langfuse | None = None


def _client() -> Langfuse:
    """Return the shared client used to read parent traces.

    Built lazily rather than at import: ``build_client`` raises when tracing is
    disabled, and the traces scope has no reason to pay for — or fail on — a
    client it never uses.

    Returns:
        The process-wide Langfuse client.
    """
    global _read_client
    if _read_client is None:
        _read_client = build_client()
    return _read_client


def _as_dict(value: Any) -> dict:
    """Coerce a Langfuse-stored payload to a dict.

    Tool observation inputs do not come back as dicts. Langfuse stores what it
    received, and for a LangChain tool call that is the ``str`` of a Python
    dict — single-quoted, so ``json.loads`` rejects it. Both encodings appear in
    practice, hence both attempts.

    Args:
        value: The stored ``input`` or ``output``.

    Returns:
        The payload as a dict, or an empty dict when it is neither a dict nor a
        string parsing to one.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    for parse in (json.loads, ast.literal_eval):
        try:
            parsed = parse(value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _text(content: Any) -> str:
    """Reduce a message's ``content`` to the words a judge should read.

    Reasoning models do not return a string here. A ``gpt-5`` reply arrives as a
    list of blocks — a ``reasoning`` block whose ``encrypted_content`` is
    kilobytes of opaque ciphertext, then the ``text`` block that is the actual
    answer. Interpolating the list instead of picking the text block hands the
    judge that ciphertext as if it were the response: every prompt metric then
    scores an answer it never saw, and the failure is invisible because the run
    still succeeds and still produces plausible-looking numbers.

    Args:
        content: A message's ``content`` — a string on classic messages, a list
            of content blocks on reasoning-model replies.

    Returns:
        The text, with non-text blocks dropped. Empty when there is none.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
    )


def _format(messages: list[Any]) -> str:
    """Flatten LangChain-serialised messages into judge-readable text.

    Args:
        messages: Serialized messages as Langfuse stored them, carrying
            ``type``, ``content`` and, on tool results, ``name``.

    Returns:
        One ``type: content`` line per message, joined by newlines. Tool results
        are truncated — a full retrieval payload would crowd out the transcript
        without changing any verdict.
    """
    lines: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = _text(message.get("content"))
        if message.get("type") == "tool":
            lines.append(f"tool {message.get('name')}: {content[:TOOL_CONTENT_LIMIT]}")
        elif content:
            lines.append(f"{message.get('type', 'unknown')}: {content}")
    return "\n".join(lines)


@lru_cache(maxsize=256)
def _parent_response(trace_id: str) -> str:
    """Fetch the assistant's answer from a tool observation's parent trace.

    The retrieval and the answer never sit on the same record: ``search_
    knowledge`` returns passages, and the answer built from them is produced
    afterwards. Faithfulness and context precision both need that answer, so
    without this lookup every RAG evaluator abstains and the observations scope
    reports a clean run that scored nothing.

    Cached because a single turn can call the tool more than once, and each of
    those observations resolves to the same trace. Never raises: a trace that
    cannot be read yields an empty response, which the evaluators skip.

    Args:
        trace_id: The observation's parent trace.

    Returns:
        The last message's text, or an empty string when it cannot be read.
    """
    try:
        trace = _client().api.trace.get(trace_id, fields=PARENT_TRACE_FIELDS)
    except Exception as e:
        logger.warning("eval_parent_trace_unreadable", trace_id=trace_id, error=str(e))
        return ""

    messages = _as_dict(trace.output).get("messages")
    if not isinstance(messages, list) or not isinstance(messages[-1] if messages else None, dict):
        return ""
    return _text(messages[-1].get("content"))


def _passages(output: Any) -> list[dict]:
    """Unwrap the passages a retrieval tool returned.

    ``search_knowledge`` returns ``list[dict]``, but that is not what the
    observation stores. LangChain wraps a tool's return value in a
    ``ToolMessage`` before the callback sees it, and Langfuse records the message:
    ``{"content": "[{...}]", "type": "tool", ...}`` — the passages as a JSON
    *string*, one level down. Reading ``output`` as a list therefore yields
    nothing, and the RAG evaluators, which abstain on empty contexts by design,
    abstain on every item while the run reports a clean pass.

    Args:
        output: The observation's stored ``output``.

    Returns:
        The passages, or an empty list when the payload holds none.
    """
    if isinstance(output, dict):
        output = output.get("content")
    if isinstance(output, str):
        for parse in (json.loads, ast.literal_eval):
            try:
                output = parse(output)
            except (ValueError, SyntaxError):
                continue
            break
    return [p for p in output if isinstance(p, dict)] if isinstance(output, list) else []


def _hops(messages: list[Any]) -> int:
    """Count the tool round-trips one turn took.

    Recorded as its own number because trace shape stopped being deterministic
    when the router became a supervisor (``docs/supervisor-architecture.md``
    §11.3). A supervisor that takes a different number of hops on the same input
    makes span-based comparisons noisier, so the answer is to score outcomes and
    keep hop count visible as a metric rather than let it quietly widen the
    variance of every other one.

    Args:
        messages: Serialized messages as Langfuse stored them.

    Returns:
        How many tool results the turn produced.
    """
    return sum(
        1 for message in messages if isinstance(message, dict) and message.get("type") == "tool"
    )


def _last_spoken(messages: list[Any]) -> int:
    """Locate the last message the assistant actually said something in.

    Usually that is the final message, but not on a turn that ends at the
    confirm ``interrupt()``: there the last message is a bare ``save_plan`` tool
    call carrying only reasoning, and the plan the user was shown sits a couple
    of messages earlier. Anchoring on the final message would make exactly the
    ``build_plan`` turns that ``plan_safety`` and ``confirm_discipline`` exist to
    judge look like turns with no output at all — silently unjudged rather than
    badly judged.

    Restricted to ``ai`` messages: a resumed turn ends ``…assistant plan, human
    "save", assistant save_plan call``, so "last message with text" alone would
    hand the judge the user's own word as the generation.

    Args:
        messages: Serialized messages as Langfuse stored them.

    Returns:
        The index of the last assistant message carrying text, or ``-1`` when
        none does.
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if (
            isinstance(message, dict)
            and message.get("type") == "ai"
            and _text(message.get("content"))
        ):
            return index
    return -1


def trace_mapper(*, item: Any, **kwargs: Any) -> EvaluatorInputs:
    """Split one turn's supervisor state into judge input and generation.

    ``item.output["messages"]`` is the whole turn: the last message the
    assistant spoke is the response, everything before it is what it was
    responding to.

    Metadata carries what a domain evaluator needs to decide a metric does not
    apply to this turn, without re-parsing the transcript or asking the judge to
    rule on its own applicability. ``verdict`` and ``repair_count`` are no longer
    among them — both were derived state on the old root graph, and derived state
    now lives in the draft store rather than in the turn's output. What replaces
    them is ``hops``: the thing that actually varies.

    Args:
        item: A fetched trace.
        **kwargs: Ignored; the Protocol passes extras.

    Returns:
        The evaluator inputs. Input and output are empty strings when the trace
        carries no usable state, which every evaluator reads as "skip".
    """
    output = _as_dict(item.output)
    messages = output.get("messages")
    if not isinstance(messages, list):
        messages = []
    spoken = _last_spoken(messages)

    return EvaluatorInputs(
        input=_format(messages[:spoken]) if spoken > 0 else "",
        output=_format(messages[spoken : spoken + 1]) if spoken >= 0 else "",
        expected_output=None,
        metadata={
            "trace_id": item.id,
            "intent": output.get("intent_hint"),
            "hops": _hops(messages),
        },
    )


async def observation_mapper(*, item: Any, **kwargs: Any) -> EvaluatorInputs:
    """Pair a ``search_knowledge`` call's query, passages and resulting answer.

    Scope is observations rather than traces because the retrieved contexts live
    on the tool observation: query and passages are already paired there, where
    on a trace you would have to work out which passages fed which answer. The
    score then lands on the retrieval span in the UI, which is where you want it
    while tuning retrieval.

    What the observation does *not* carry is the answer, so it is fetched from
    the parent trace — option (1) of ``references/rag-ragas.md`` §3, one extra
    read per item, cached per trace. Async so that read happens off the event
    loop; the batch runner awaits a coroutine mapper.

    Args:
        item: A fetched observation, expected to be a ``search_knowledge`` call.
        **kwargs: Ignored; the Protocol passes extras.

    Returns:
        The evaluator inputs, with the passage texts under
        ``metadata["contexts"]`` and the answer under ``metadata["response"]``.
    """
    passages = _passages(item.output)
    contexts = [p.get("text", "") for p in passages]
    sources = [p.get("source") for p in passages]

    trace_id = getattr(item, "trace_id", None)
    response = await asyncio.to_thread(_parent_response, trace_id) if trace_id else ""

    return EvaluatorInputs(
        input=_as_dict(item.input).get("query", ""),
        output=passages,
        expected_output=None,
        metadata={
            "observation_id": item.id,
            "trace_id": trace_id,
            "contexts": contexts,
            "sources": sources,
            "response": response,
        },
    )


__all__ = ["observation_mapper", "trace_mapper"]
