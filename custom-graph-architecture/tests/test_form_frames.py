"""How a suspended form crosses the API: the frame it goes out on, and the resume it comes back as.

The graph pauses on the profile form the same way it pauses for a plan approval, but the
two resume from different things — one from a sentence the user typed, the other from
fields they filled in. This is the seam that has to tell them apart.
"""

from types import SimpleNamespace

from langgraph.types import Command

from src.nodes import PLAN_APPROVAL_INTERRUPT, PROFILE_FORM_INTERRUPT
from src.runtime.facade import LangGraphRuntime, _pending_form

FORM = {
    "type": PROFILE_FORM_INTERRUPT,
    "summary": "A few details first.",
    "fields": [{"name": "age"}],
    "values": {},
    "errors": {},
}

USER_ID = "user-1"


def _suspended_on(value: object) -> SimpleNamespace:
    """A run parked at an interrupt carrying this payload."""
    task = SimpleNamespace(interrupts=(SimpleNamespace(value=value),))
    return SimpleNamespace(values={"messages": []}, next=("some_node",), tasks=(task,))


# --- Going out ---------------------------------------------------------------------------


def test_a_suspended_form_is_read_off_the_run() -> None:
    """The client cannot render what it is not told about."""
    assert _pending_form(_suspended_on(FORM)) == FORM


def test_an_approval_gate_is_not_a_form() -> None:
    """Both pauses look alike from outside; only one has fields to fill in, and treating
    a plan approval as a form would replace the yes/no with an empty form."""
    approval = {"type": PLAN_APPROVAL_INTERRUPT, "summary": "Approve this plan?"}

    assert _pending_form(_suspended_on(approval)) is None


def test_a_settled_run_has_no_form() -> None:
    """Nothing is waiting, so nothing is asked for."""
    settled = SimpleNamespace(values={"messages": []}, next=(), tasks=())

    assert _pending_form(settled) is None


# --- Coming back ------------------------------------------------------------------------


class _FakeGraph:
    """Stands in for the compiled graph: reports one state and records nothing else."""

    def __init__(self, state: SimpleNamespace) -> None:
        self.state = state

    async def aget_state(self, _config: dict) -> SimpleNamespace:
        return self.state


async def _input(state: SimpleNamespace, form_data: dict | None) -> object:
    """What the facade would feed the graph for this turn."""
    run_input, _ = await LangGraphRuntime()._graph_input(
        _FakeGraph(state), {}, [], USER_ID, form_data
    )
    return run_input


async def test_a_paused_run_resumes_from_the_submitted_fields() -> None:
    """The form's answer is the fields, not the message body they were posted with —
    resuming from the text would reach the node as an empty submission and re-ask."""
    run_input = await _input(_suspended_on(FORM), {"age": 27})

    assert isinstance(run_input, Command)
    assert run_input.resume == {"age": 27}


async def test_a_paused_run_without_fields_still_resumes_from_the_text() -> None:
    """The plan approval shares this path and answers in prose."""
    run_input = await _input(_suspended_on({"type": PLAN_APPROVAL_INTERRUPT}), None)

    assert isinstance(run_input, Command)
    assert run_input.resume == ""


async def test_fields_posted_to_a_run_that_is_not_paused_start_a_turn() -> None:
    """A stale form submitted after the run moved on must not be mistaken for a resume."""
    settled = SimpleNamespace(values={"messages": []}, next=(), tasks=())

    run_input = await _input(settled, {"age": 27})

    assert not isinstance(run_input, Command)
    assert run_input["user_id"] == USER_ID
