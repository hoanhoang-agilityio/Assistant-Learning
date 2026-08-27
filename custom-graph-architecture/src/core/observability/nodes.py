"""Node instrumentation: latency, outcome and trace attributes, decided in one place.

Nodes carry no observability code of their own. ``observed`` wraps each one where it is
added to the graph, so what a run records is a property of the graph rather than of
twenty-one node bodies that would each have to be kept in step.

Every Langfuse call here is best-effort. Tracing failing is not a reason for a turn to
fail, so nothing in this module may raise out of the node it wraps.
"""

from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from time import perf_counter
from typing import Any

from langgraph.errors import GraphInterrupt

from src.core.observability.langfuse import get_langfuse_client
from src.enums import Node
from src.schemas import GraphState
from src.utils.logging import logger

NodeFn = Callable[[GraphState], Awaitable[dict[str, Any]]]

# The state a node writes that spec §10 asks a trace to be searchable by. Read off the
# update rather than the state, so a line says what *this* node decided, not what the
# run happened to be carrying when it ran.
TRACKED_FIELDS: tuple[str, ...] = (
    "intent",
    "guard_blocked",
    "block_reason",
    "context_complete",
    "missing_fields",
    "user_info_retry_count",
    "coach_retry_count",
    "hitl_decision",
    "hitl_retry_count",
    "faithfulness_score",
    "qa_retry_count",
)


def _elapsed_ms(started: float) -> float:
    """Milliseconds since a ``perf_counter`` reading, at the resolution a log needs."""

    return round((perf_counter() - started) * 1000, 2)


def _verification_summary(result: dict | None) -> dict[str, Any]:
    """A verification verdict small enough to sit on a span, without the issue text."""

    if result is None:
        return {"verification_passed": True}

    issues = result.get("issues", [])
    return {
        "verification_passed": False,
        "verification_issue_count": len(issues),
        "verification_failed_checks": sorted(
            {issue["check"] for issue in issues if issue.get("check")}
        ),
    }


def _retrieval_summary(chunks: list[dict] | None) -> dict[str, Any]:
    """What retrieval returned and how close it was, which is what tunes the threshold."""

    if not chunks:
        return {"retrieved_chunks": 0}

    scores = [chunk["score"] for chunk in chunks]
    return {
        "retrieved_chunks": len(chunks),
        "retrieval_scores": scores,
        "retrieval_top_score": max(scores),
    }


def observations(update: Mapping[str, Any]) -> dict[str, Any]:
    """The observable fields of one node's state update."""

    fields: dict[str, Any] = {
        key: update[key] for key in TRACKED_FIELDS if key in update
    }

    if "verification_result" in update:
        fields |= _verification_summary(update["verification_result"])
    if "retrieved_context" in update:
        fields |= _retrieval_summary(update["retrieved_context"])
    if update.get("plan") is not None:
        fields["plan_generated"] = True
    if update.get("final_message"):
        fields["final_message"] = update["final_message"]

    return fields


def _record_span(
    node: str, duration_ms: float, fields: Mapping[str, Any], error: str | None = None
) -> None:
    """Attach this node's timing and decisions to the span the callback handler opened."""

    client = get_langfuse_client()
    if client is None:
        return

    try:
        client.update_current_span(
            metadata={"node": node, "duration_ms": duration_ms, **fields},
            level="ERROR" if error else "DEFAULT",
            status_message=error,
        )
    except Exception as trace_error:
        logger.debug("trace_span_update_failed", node=node, error=str(trace_error))


def _record_scores(update: Mapping[str, Any]) -> None:
    """Promote the two gate results to trace scores, which is what Langfuse can chart."""

    client = get_langfuse_client()
    if client is None:
        return

    try:
        score = update.get("faithfulness_score")
        if "faithfulness_score" in update and score is not None:
            client.score_current_trace(
                name="faithfulness", value=float(score), data_type="NUMERIC"
            )
        if "verification_result" in update:
            client.score_current_trace(
                name="plan_verification",
                value=float(update["verification_result"] is None),
                data_type="BOOLEAN",
            )
    except Exception as trace_error:
        logger.debug("trace_score_failed", error=str(trace_error))


def observed(name: Node, node: NodeFn) -> NodeFn:
    """Wrap a node so its latency, its decisions and its failures are all recorded."""

    @wraps(node)
    async def run(state: GraphState) -> dict[str, Any]:
        started = perf_counter()

        try:
            update = await node(state)
        except GraphInterrupt:
            # A pause is the node doing its job. LangGraph raises it to park the run, and
            # logging it as a failure would make every HITL turn look like an error.
            raise
        except Exception as error:
            duration_ms = _elapsed_ms(started)
            logger.exception(
                "node_failed",
                node=name.value,
                duration_ms=duration_ms,
                error=str(error),
            )
            _record_span(name.value, duration_ms, {}, error=str(error))
            raise

        duration_ms = _elapsed_ms(started)
        fields = observations(update or {})
        logger.info(
            "node_completed", node=name.value, duration_ms=duration_ms, **fields
        )
        _record_span(name.value, duration_ms, fields)
        _record_scores(update or {})
        return update

    return run


__all__ = ["TRACKED_FIELDS", "observations", "observed"]
