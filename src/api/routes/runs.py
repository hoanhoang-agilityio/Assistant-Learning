from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.deps import get_orchestrator
from api.schemas import CreateRunRequest, ResumeRunRequest, RunStatusResponse
from api.serializers import to_run_status_response
from core.graph.service import RunNotFoundError, RunOrchestrator
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
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    return to_run_status_response(run_status)


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
            pending_tool=payload.pending_tool,
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
