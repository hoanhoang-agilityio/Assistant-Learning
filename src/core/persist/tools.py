from langchain_core.tools import BaseTool, tool

from core.persist.utils import (
    save_artifacts_data,
    save_metrics_data,
    save_run_data,
)


@tool
def save_run(run_id: str, thread_id: str, orchestration_state: dict) -> dict:
    """Persist run metadata and orchestration snapshot."""
    return save_run_data(run_id, thread_id, orchestration_state)


@tool
def save_metrics(
    run_id: str,
    faithfulness_score: float | None,
    verification_report: dict,
) -> dict:
    """Persist evaluation metrics for the completed run."""
    return save_metrics_data(run_id, faithfulness_score, verification_report)


@tool
def save_artifacts(run_id: str, workspace_path: str) -> dict:
    """Copy verified artifacts to final/ and write persist logs."""
    del run_id
    return save_artifacts_data(workspace_path)


PERSIST_TOOLS: list[BaseTool] = [
    save_run,
    save_metrics,
    save_artifacts,
]
