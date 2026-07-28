import json
import queue
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from api.deps import get_orchestrator
from api.schemas import (
    ContinueRunRequest,
    CreateRunRequest,
    ResumeRunRequest,
    RunStatusResponse,
    RunSummaryResponse,
)
from api.serializers import to_run_status_response, to_run_summary_response
from core.graph.service import RunEvent, RunNotFoundError, RunOrchestrator, RunStatus
from core.rate_limit import RateLimitExceededError

router = APIRouter(prefix="/runs", tags=["runs"])


def _resolve_user_id(
    payload_user_id: str | None,
    header_user_id: str | None,
) -> str | None:
    header = (header_user_id or "").strip()
    if header:
        return header
    body = (payload_user_id or "").strip()
    return body or None


@router.post("", response_model=RunStatusResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: CreateRunRequest,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> RunStatusResponse:
    """Create a run and execute the graph until the next interrupt or completion."""
    user_id = _resolve_user_id(payload.user_id, x_user_id)
    try:
        run_status = orchestrator.start_run(
            query=payload.query,
            user_profile=payload.user_profile,
            constraints=payload.constraints,
            user_id=user_id,
            submitted_plan_text=payload.submitted_plan_text,
            idempotency_key=payload.idempotency_key,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    return to_run_status_response(run_status)


@router.get("", response_model=list[RunSummaryResponse])
def list_runs(
    user_id: str | None = Query(
        default=None, description="Filter by user id (X-User-Id header wins)."
    ),
    limit: int = Query(default=50, ge=1, le=100),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[RunSummaryResponse]:
    """Return recent runs for a user, newest first."""
    resolved_user_id = _resolve_user_id(user_id, x_user_id)
    if not resolved_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id query parameter or X-User-Id header is required",
        )
    summaries = orchestrator.list_runs(resolved_user_id, limit=limit)
    return [to_run_summary_response(summary) for summary in summaries]


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(
    run_id: str,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
) -> RunStatusResponse:
    """Return current run status from the LangGraph checkpointer."""
    try:
        run_status = orchestrator.get_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return to_run_status_response(run_status)


@router.post("/{run_id}/resume", response_model=RunStatusResponse)
def resume_run(
    run_id: str,
    payload: ResumeRunRequest,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
) -> RunStatusResponse:
    """Resume a run paused at HITL with user input."""
    try:
        run_status = orchestrator.resume_run(
            run_id,
            user_response=payload.user_response,
            approval_status=payload.approval_status,
            decision_type=payload.decision_type,
            message=payload.message,
            form_data=payload.form_data,
            submitted_plan_text=payload.submitted_plan_text,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    return to_run_status_response(run_status)


@router.post("/{run_id}/continue", response_model=RunStatusResponse)
def continue_run(
    run_id: str,
    payload: ContinueRunRequest,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
) -> RunStatusResponse:
    """Replan within an existing conversation when the user changes plan preferences."""
    try:
        run_status = orchestrator.continue_run(run_id, message=payload.message)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    return to_run_status_response(run_status)


def _step_id_from_chunk(chunk: tuple[tuple[str, ...], dict]) -> Iterator[str]:
    """Map one graph.stream(subgraphs=True) chunk to "subgraph:node" step ids.

    Mirrors the "{subgraph}:{node}" convention core/subgraphs/wrapper.py already
    writes into RunStatus.steps, so the frontend can map a streamed step id
    through the same STEP_COPY dictionary it already uses for polling -- no new
    copy/mapping table for the streaming path. A top-level node (empty
    namespace) yields its bare name (e.g. "hitl", "persist"), matching those
    same bare-name STEP_COPY entries. "__interrupt__" is LangGraph's own pseudo
    node marking a paused run, not a step a user should see -- skipped.
    """
    namespace, updates = chunk
    subgraph_name = namespace[0].split(":", 1)[0] if namespace else None
    for node_name in updates:
        if node_name == "__interrupt__":
            continue
        yield f"{subgraph_name}:{node_name}" if subgraph_name else node_name


def _format_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _run_settled_event(run_status: RunStatus) -> str:
    return _format_sse(
        {"type": "run_settled", "run": to_run_status_response(run_status).model_dump()}
    )


def _iter_run_events(
    event_queue: "queue.Queue[RunEvent] | None",
    initial_status: RunStatus,
) -> Iterator[str]:
    """SSE body for GET /runs/{run_id}/events.

    If the run isn't currently executing (event_queue is None -- already
    settled, or paused on HITL), emit one run_settled event from the current
    snapshot and close; a narrow race can leave event_queue None a moment after
    a run genuinely finishes starting up (opened synchronously in start_run et
    al., but this read can still land just before that), in which case the
    client sees one settled event still reporting "running" and should
    reconnect -- the existing polling endpoint remains available as a fallback
    either way. Otherwise, stream each LangGraph node update as it arrives,
    ending with exactly one run_settled event.
    """
    if event_queue is None:
        yield _run_settled_event(initial_status)
        return
    while True:
        event = event_queue.get()
        if event.kind == "run_settled":
            assert event.status is not None
            yield _run_settled_event(event.status)
            return
        assert event.chunk is not None
        for step in _step_id_from_chunk(event.chunk):
            yield _format_sse({"type": "node_update", "step": step})


@router.get("/{run_id}/events")
def stream_run_events(
    run_id: str,
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    """Stream this run's LangGraph node-lifecycle events over SSE.

    Complements GET /runs/{run_id} (kept for polling clients): while a run is
    executing, each event carries the step id of the subgraph/node that just
    completed -- real-time, at the same granularity LangGraph itself reports,
    rather than only once the whole run settles. The stream always ends with
    one run_settled event carrying the same status shape /runs/{run_id}
    returns.
    """
    try:
        initial_status = orchestrator.get_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    event_queue = orchestrator.get_event_queue(run_id)
    return StreamingResponse(
        _iter_run_events(event_queue, initial_status),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
