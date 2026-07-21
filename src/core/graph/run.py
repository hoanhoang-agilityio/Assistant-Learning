from pathlib import Path

from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.vfs.bootstrap import init_run_workspace


def create_initial_state(
    *,
    run_id: str,
    thread_id: str,
    query: str,
    user_profile: dict | None = None,
    constraints: dict | None = None,
    workspace_root: Path | None = None,
    user_id: str | None = None,
) -> OrchestrationState:
    """Bootstrap run workspace and return default orchestration state."""
    workspace_path = init_run_workspace(run_id, workspace_root=workspace_root)
    settings = get_settings()
    resolved_user_id = (user_id or "").strip() or settings.rate_limit_default_user_id
    return OrchestrationState(
        run_id=run_id,
        thread_id=thread_id,
        user_id=resolved_user_id,
        current_node="supervisor",
        query=query,
        user_profile=user_profile or {},
        constraints=constraints or {},
        profile_complete=False,
        profile_valid=False,
        days_per_week_explicit=False,
        request_type=None,
        affected_domains=[],
        route_decision=None,
        retry_count=0,
        replan_count=0,
        verification_passed=False,
        faithfulness_score=None,
        waiting_for_user=False,
        approval_status=None,
        user_response=None,
        revision_feedback=None,
        workspace_path=str(workspace_path),
        final_artifact_path=None,
        refusal_message=None,
        steps=[],
        approved_tools=[],
        pending_tool=None,
    )
