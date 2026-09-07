"""Every terminal outcome of a plan review hands the approval fields back cleared.

State is checkpointed per conversation, so a decision left standing outlives the plan it
was about. Without this, the next plan the same thread asks for is built against the last
one's rejection — its text arrives as ``<reviewer_feedback>``, and its retry budget is
already part spent, so a fresh plan can reach ``hitl_exhausted`` having been revised once.
"""

import sys

import pytest

from src.configs.config import settings
from src.enums import PlanApprovalRoute
from src.nodes.commit_plan import commit_plan
from src.nodes.hitl_exhausted import hitl_exhausted
from src.nodes.hitl_rejected_no_feedback import hitl_rejected_no_feedback
from src.nodes.plan_approval import route_after_plan_approval
from src.schemas import GraphState, PendingApproval, initial_state

# ``src.nodes`` re-exports the function under its own module's name, so importing the
# module by path binds the function instead.
commit_plan_module = sys.modules[commit_plan.__module__]

USER_ID = "user-1"

APPROVAL_FIELDS = (
    "pending_approval",
    "approval_decision",
    "approval_feedback",
    "approval_retry_count",
)


def _reviewed(decision: str, feedback: str | None, retry_count: int) -> GraphState:
    """State as a review leaves it, on its way to one of the terminal nodes."""
    return initial_state("build me a plan", USER_ID) | {
        "plan": {"summary": "a plan"},
        "pending_approval": PendingApproval(
            source="coach_agent", kind="plan", summary="Approve?", payload={}
        ),
        "approval_decision": decision,
        "approval_feedback": feedback,
        "approval_retry_count": retry_count,
    }


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record the plan write instead of reaching long-term memory."""
    writes: list[dict] = []

    async def save_plan(_user_id: str, plan: dict) -> dict:
        writes.append(plan)
        return plan

    monkeypatch.setattr(commit_plan_module, "save_plan", save_plan)
    return writes


def _assert_cleared(update: dict) -> None:
    """Every approval field is handed back at its starting value, not just dropped."""
    assert update["pending_approval"] is None
    assert update["approval_decision"] is None
    assert update["approval_feedback"] is None
    assert update["approval_retry_count"] == 0


# --- The three terminal outcomes ---------------------------------------------------------


async def test_committing_an_approved_plan_closes_the_review(saved) -> None:
    """An approved plan is finished with; nothing about its review belongs to the next one."""
    update = await commit_plan(_reviewed("approve", None, 0))

    _assert_cleared(update)
    assert saved == [{"summary": "a plan"}]


async def test_a_rejection_with_no_feedback_closes_the_review() -> None:
    """The branch ends here, so the rejection must not follow the user into a new request."""
    update = await hitl_rejected_no_feedback(_reviewed("reject", None, 0))

    _assert_cleared(update)


async def test_an_exhausted_budget_closes_the_review() -> None:
    """The sharpest case: a spent budget carried over would cut the next plan's revisions short."""
    update = await hitl_exhausted(
        _reviewed("reject", "still wrong", settings.HITL_MAX_RETRIES)
    )

    _assert_cleared(update)


async def test_a_terminal_node_still_says_its_piece(saved) -> None:
    """Clearing the fields must not cost the message the node exists to write."""
    update = await commit_plan(_reviewed("approve", None, 0))

    assert update["messages"]


# --- The one outcome that must NOT clear ---------------------------------------------------


def test_a_revise_is_not_a_terminal_outcome() -> None:
    """The coach is handed the feedback precisely so it can act on it, so the revise route
    goes back to ``coach_agent`` rather than through a node that would clear it."""
    state = _reviewed("reject", "swap the bench press", 0)

    assert route_after_plan_approval(state) == PlanApprovalRoute.COACH_REVISE


async def test_a_committed_plan_leaves_no_field_behind(saved) -> None:
    """A field added to the cycle later must be added to the reset too."""
    update = await commit_plan(_reviewed("approve", None, 0))

    assert set(APPROVAL_FIELDS) <= set(update)
