"""Integration checks for intent-classification accuracy on clear example queries."""

import pytest

from src.services.intent import classify_user_intent

_INTENT_CASES = [
    pytest.param(
        "Build me a 4 day hypertrophy plan for dumbbells only at home.",
        "coaching",
        id="coaching-new-plan",
    ),
    pytest.param(
        "My knees hurt during lunges. Update my workout plan to avoid that movement.",
        "coaching",
        id="coaching-plan-revision",
    ),
    pytest.param(
        "How much protein per kilogram should I eat to build muscle?",
        "qa",
        id="qa-protein-guidance",
    ),
    pytest.param(
        "Does creatine help strength training, and when should I take it?",
        "qa",
        id="qa-supplement-question",
    ),
    pytest.param(
        "Write me a SQL migration for a users table.",
        "off_topic",
        id="off-topic-sql",
    ),
    pytest.param(
        "Plan a three day trip to Tokyo for me.",
        "off_topic",
        id="off-topic-travel",
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize(("user_query", "expected_intent"), _INTENT_CASES)
async def test_classifier_matches_clear_reference_queries(
    require_openai_key: None, user_query: str, expected_intent: str
) -> None:
    """The classifier should get obvious, representative examples right."""
    actual_intent = await classify_user_intent(user_query)
    assert actual_intent == expected_intent
