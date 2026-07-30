from pathlib import Path

from core.adapters.vfs import VFS
from core.adapters.vfs.bootstrap import init_run_workspace
from core.adapters.vfs.layout import PLAN_SUBMITTED_TEXT
from core.config.settings import get_settings
from core.orchestration.agents.state import OrchestrationState
from core.shared.profile.store import seed_profile


def create_initial_state(
    *,
    run_id: str,
    thread_id: str,
    query: str,
    user_profile: dict | None = None,
    constraints: dict | None = None,
    workspace_root: Path | None = None,
    user_id: str | None = None,
    submitted_plan_text: str | None = None,
) -> OrchestrationState:
    """Bootstrap run workspace and return default orchestration state."""
    workspace_path = init_run_workspace(run_id, workspace_root=workspace_root)
    seed_profile(str(workspace_path), user_profile or {}, constraints or {})
    if submitted_plan_text:
        VFS.for_run(workspace_path).write(PLAN_SUBMITTED_TEXT, submitted_plan_text)
    settings = get_settings()
    resolved_user_id = (user_id or "").strip() or settings.rate_limit_default_user_id
    return OrchestrationState(
        run_id=run_id,
        thread_id=thread_id,
        user_id=resolved_user_id,
        current_node="supervisor",
        query=query,
        fitness_query=None,
        scope_result=None,
        execution_context=None,
        intent=None,
        profile_complete=False,
        profile_valid=False,
        days_per_week_explicit=False,
        submitted_plan_text=submitted_plan_text,
        active_capability=None,
        capability_results={},
        last_capability_result=None,
        verification_passed=False,
        faithfulness_score=None,
        verification_retry_target=None,
        verification_feedback=None,
        verification_retry_count=0,
        hop_count=0,
        agent_trail=[],
        next_agent=None,
        waiting_for_user=False,
        approval_status=None,
        user_response=None,
        revision_feedback=None,
        revision_count=0,
        workspace_path=str(workspace_path),
        final_artifact_path=None,
        final_response=None,
        refusal_message=None,
        run_complete=False,
        steps=[],
    )
