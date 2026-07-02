from core.agents.state import OrchestrationState
from core.agents.supervisor_log import load_verification_report
from core.persist.tools import save_artifacts, save_metrics, save_run
from core.persist.utils import persist_trigger_data, write_metrics_artifact
from core.subgraphs.wrapper import merge_subgraph_updates


def invoke_persist_node(state: OrchestrationState) -> dict:
    """Run PERSIST_RESULTS after supervisor persist_trigger guards pass."""
    trigger = persist_trigger_data(
        verification_passed=state["verification_passed"],
        faithfulness_score=state["faithfulness_score"],
        approval_status=state["approval_status"],
    )
    if not trigger["can_persist"]:
        return merge_subgraph_updates(
            state,
            {
                "current_node": "persist",
                "waiting_for_user": True,
                "approval_status": state["approval_status"] or "pending",
            },
            subgraph="persist",
            steps=["persist_trigger_blocked"],
        )

    orchestration_snapshot = dict(state)
    save_run.invoke(
        {
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
            "orchestration_state": orchestration_snapshot,
        }
    )

    verification_report = load_verification_report(state["workspace_path"])
    metrics = save_metrics.invoke(
        {
            "run_id": state["run_id"],
            "faithfulness_score": state["faithfulness_score"],
            "verification_report": verification_report,
        }
    )
    write_metrics_artifact(state["workspace_path"], metrics)

    artifacts = save_artifacts.invoke(
        {
            "run_id": state["run_id"],
            "workspace_path": state["workspace_path"],
        }
    )

    return merge_subgraph_updates(
        state,
        {
            "current_node": "persist",
            "final_artifact_path": artifacts["final_artifact_path"],
            "waiting_for_user": False,
        },
        subgraph="persist",
        steps=["save_run", "save_metrics", "save_artifacts"],
    )
