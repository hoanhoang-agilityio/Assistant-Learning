"""Tests for compact LLM payload helpers."""

from core.adapters.llm.payload import compact_json, limit_feedback_items, strip_empty_values


def test_strip_empty_values_removes_null_and_empty_collections() -> None:
    payload = {
        "profile": {"age": 30, "sex": None},
        "feedback": [],
        "notes": "",
        "nested": {"empty_list": [], "value": "ok"},
    }
    cleaned = strip_empty_values(payload)
    assert cleaned == {"profile": {"age": 30}, "nested": {"value": "ok"}}


def test_compact_json_uses_minified_format() -> None:
    payload = {"goal": "fat_loss", "tasks": ["one", "two"]}
    serialized = compact_json(payload)
    assert serialized == '{"goal":"fat_loss","tasks":["one","two"]}'


def test_limit_feedback_items_deduplicates_and_caps() -> None:
    feedback = ["issue one", "issue one", "issue two", "issue three", "issue four", "issue five"]
    limited = limit_feedback_items(feedback, max_items=3)
    assert limited == ["issue one", "issue two", "issue three"]
