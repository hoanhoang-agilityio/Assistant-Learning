from langchain_core.tools import BaseTool, tool


@tool
def save_run(run_id: str, thread_id: str, orchestration_state: dict) -> dict:
    """Persist run metadata and orchestration snapshot."""
    ...


@tool
def save_metrics(
    run_id: str,
    faithfulness_score: float | None,
    verification_report: dict,
) -> dict:
    """Persist evaluation metrics for the completed run."""
    ...


@tool
def save_artifacts(run_id: str, workspace_path: str) -> dict:
    """Copy verified artifacts to final/ and write persist logs."""
    ...


PERSIST_TOOLS: list[BaseTool] = [
    save_run,
    save_metrics,
    save_artifacts,
]
