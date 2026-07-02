from typing import Any

from core.agents.state import OrchestrationState


def append_pipeline_steps(
    state: OrchestrationState,
    subgraph: str,
    step_names: list[str],
) -> list[str]:
    """Append subgraph step ids and return the merged pipeline steps list."""
    prefix = f"{subgraph}:"
    existing = list(state.get("steps") or [])
    new_steps = [f"{prefix}{name}" for name in step_names]
    merged: list[str] = []
    seen: set[str] = set()
    for step in [*existing, *new_steps]:
        if step in seen:
            continue
        seen.add(step)
        merged.append(step)
    return merged


def merge_subgraph_updates(
    state: OrchestrationState,
    updates: dict[str, Any],
    *,
    subgraph: str,
    steps: list[str],
) -> dict[str, Any]:
    """Merge orchestration updates with deduplicated pipeline step tracking."""
    return {
        **updates,
        "steps": append_pipeline_steps(state, subgraph, steps),
    }
