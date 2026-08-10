"""Turn a fetched Langfuse item into the inputs an evaluator is given.

``item`` is keyword-only. The SDK's own docstring shows ``def mapper(trace):``,
which does not satisfy the ``MapperFunction`` Protocol it is documenting —
``__call__(self, *, item, **kwargs)``. Passing it positionally raises.

Nothing here may raise on a malformed item: the mapper runs once per fetched
trace, and one bad shape must not end the run. Missing pieces come back as empty
strings, which the evaluators treat as "abstain".
"""

import ast
import json
from typing import Any

from langfuse import EvaluatorInputs

TOOL_CONTENT_LIMIT = 300


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
        content = message.get("content") or ""
        if message.get("type") == "tool":
            lines.append(f"tool {message.get('name')}: {content[:TOOL_CONTENT_LIMIT]}")
        elif content:
            lines.append(f"{message.get('type', 'unknown')}: {content}")
    return "\n".join(lines)


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


def trace_mapper(*, item: Any, **kwargs: Any) -> EvaluatorInputs:
    """Split one turn's supervisor state into judge input and generation.

    ``item.output["messages"]`` is the whole turn: everything but the last
    message is what the assistant was responding to, the last message is the
    response.

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

    return EvaluatorInputs(
        input=_format(messages[:-1]),
        output=_format(messages[-1:]),
        expected_output=None,
        metadata={
            "trace_id": item.id,
            "intent": output.get("intent_hint"),
            "hops": _hops(messages),
        },
    )


def observation_mapper(*, item: Any, **kwargs: Any) -> EvaluatorInputs:
    """Pair a ``search_knowledge`` call's query with the passages it returned.

    Scope is observations rather than traces because the retrieved contexts live
    on the tool observation: query and passages are already paired there, where
    on a trace you would have to work out which passages fed which answer.

    The assistant's answer is *not* on this observation — it is produced after
    the tool returns — so ``output`` here is the retrieval itself. Faithfulness
    needs a response, so ``rag.py`` abstains unless one is supplied; see
    ``references/rag-ragas.md`` §3 for the parent-trace fetch that would provide
    it.

    Args:
        item: A fetched observation, expected to be a ``search_knowledge`` call.
        **kwargs: Ignored; the Protocol passes extras.

    Returns:
        The evaluator inputs, with the passage texts under
        ``metadata["contexts"]``.
    """
    passages = item.output if isinstance(item.output, list) else []
    contexts = [p.get("text", "") for p in passages if isinstance(p, dict)]
    sources = [p.get("source") for p in passages if isinstance(p, dict)]

    return EvaluatorInputs(
        input=_as_dict(item.input).get("query", ""),
        output=item.output,
        expected_output=None,
        metadata={
            "observation_id": item.id,
            "trace_id": getattr(item, "trace_id", None),
            "contexts": contexts,
            "sources": sources,
        },
    )


__all__ = ["observation_mapper", "trace_mapper"]
