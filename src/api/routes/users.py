from fastapi import APIRouter, Depends, Query

from api.deps import get_orchestrator
from api.schemas import RunSummaryResponse
from api.serializers import to_run_summary_response
from core.graph.service import RunOrchestrator

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}/runs", response_model=list[RunSummaryResponse])
def list_user_runs(
    user_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
) -> list[RunSummaryResponse]:
    """Return recent runs for the given user, newest first."""
    summaries = orchestrator.list_runs(user_id, limit=limit)
    return [to_run_summary_response(summary) for summary in summaries]
