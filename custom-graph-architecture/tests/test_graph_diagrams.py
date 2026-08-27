"""The exported diagrams are regenerated from the graph, so they cannot drift from it."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.export_graph_diagrams import (  # noqa: E402
    OUTPUT_DIR,
    PLAN,
    VIEWS,
    branch_view,
    graph_edges,
    to_mermaid,
)


def _markup(view_name: str) -> str:
    """The picture the current graph would produce for one view."""
    return to_mermaid(
        branch_view(graph_edges(), VIEWS[view_name]), view_name.replace("-", " ")
    )


@pytest.mark.parametrize("view_name", sorted(VIEWS))
def test_the_committed_diagram_matches_the_graph(view_name: str) -> None:
    """A diagram that disagrees with the wiring is worse than no diagram at all."""
    committed = (OUTPUT_DIR / f"{view_name}.mmd").read_text()

    assert committed == _markup(view_name), (
        f"run `uv run python scripts/export_graph_diagrams.py` to redraw {view_name}"
    )


@pytest.mark.parametrize("view_name", sorted(VIEWS))
def test_the_plan_renders_the_same_picture(view_name: str) -> None:
    """The doc carries its own copy, and a stale copy is what readers would actually see."""
    assert _markup(view_name).strip() in PLAN.read_text()


def test_each_branch_view_stops_at_the_other_branchs_fork() -> None:
    """The whole point of two pictures: neither shows the agent the other one runs."""
    coaching = _markup("coaching-flow")
    qa = _markup("qa-flow")

    assert "qa_agent" not in coaching
    assert "coach_agent" not in qa
    assert "load_user_context" in coaching and "load_user_context" in qa
    assert "finalize_turn" in coaching and "finalize_turn" in qa


def test_the_whole_workflow_view_holds_both_branches() -> None:
    """The third picture is the one that has to show the fork the other two split on."""
    workflow = _markup("workflow")

    assert "coach_agent" in workflow
    assert "qa_agent" in workflow
