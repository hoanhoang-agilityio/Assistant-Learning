import pytest
from pydantic import ValidationError

from api.schemas import ContinueRunRequest, CreateRunRequest


def test_create_run_request_rejects_oversized_query() -> None:
    """Regression test for A10: an ingress-level cap must reject a
    pathologically large query before it ever reaches token-estimation or
    per-user cost/rate limiting."""
    with pytest.raises(ValidationError):
        CreateRunRequest(query="x" * 4001)


def test_create_run_request_accepts_query_at_the_cap() -> None:
    request = CreateRunRequest(query="x" * 4000)
    assert len(request.query) == 4000


def test_continue_run_request_rejects_oversized_message() -> None:
    with pytest.raises(ValidationError):
        ContinueRunRequest(message="x" * 4001)


def test_continue_run_request_accepts_message_at_the_cap() -> None:
    request = ContinueRunRequest(message="x" * 4000)
    assert len(request.message) == 4000


def test_create_run_request_submitted_plan_text_optional() -> None:
    """Phase 4: omitting submitted_plan_text is fully backward compatible."""
    request = CreateRunRequest(query="check my plan")
    assert request.submitted_plan_text is None


def test_create_run_request_accepts_submitted_plan_text() -> None:
    request = CreateRunRequest(query="check my plan", submitted_plan_text="Day 1: Squat 3x5")
    assert request.submitted_plan_text == "Day 1: Squat 3x5"
