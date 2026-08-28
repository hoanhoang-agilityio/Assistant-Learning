"""Tests for the long-term store namespace scheme."""

import pytest

from src.runtime.namespaces import MemoryScope, namespace_for


def test_namespace_is_scoped_by_user_then_kind() -> None:
    """The user segment comes before the scope so a user's memory stays contiguous."""
    assert namespace_for("u-1", MemoryScope.PREFERENCES) == (
        "users",
        "u-1",
        "preferences",
    )
    assert namespace_for("u-1", MemoryScope.KNOWLEDGE) == ("users", "u-1", "knowledge")
    assert namespace_for("u-1", MemoryScope.FACTS) == ("users", "u-1", "facts")


def test_empty_user_id_is_rejected() -> None:
    """An anonymous write would pool one caller's memory into a shared namespace."""
    with pytest.raises(ValueError, match="user_id is required"):
        namespace_for("", MemoryScope.FACTS)


def test_scopes_match_the_three_categories_in_the_spec() -> None:
    """Preferences, accumulated knowledge and facts — no more, no fewer."""
    assert {scope.value for scope in MemoryScope} == {
        "preferences",
        "knowledge",
        "facts",
    }
