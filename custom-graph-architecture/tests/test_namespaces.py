"""Tests for the long-term store namespace scheme."""

import pytest

from src.runtime.namespaces import MemoryScope, namespace_for, plan_namespace


def test_namespace_is_scoped_by_user_then_kind() -> None:
    """The user segment comes before the scope so a user's memory stays contiguous."""
    assert namespace_for("u-1", MemoryScope.FACTS) == ("users", "u-1", "facts")


def test_the_plan_lives_beside_the_scopes_rather_than_inside_one() -> None:
    """A plan is one document, not a keyed scope, and must not collide with the facts."""
    assert plan_namespace("u-1") == ("users", "u-1", "plan")
    assert plan_namespace("u-1") != namespace_for("u-1", MemoryScope.FACTS)


def test_empty_user_id_is_rejected() -> None:
    """An anonymous write would pool one caller's memory into a shared namespace."""
    with pytest.raises(ValueError, match="user_id is required"):
        namespace_for("", MemoryScope.FACTS)

    with pytest.raises(ValueError, match="user_id is required"):
        plan_namespace("")


def test_facts_is_the_only_scope_with_a_writer() -> None:
    """The spec named three. A scope nothing fills answers empty for every user, so the
    two the supervisor migration orphaned were removed rather than left addressable."""
    assert {scope.value for scope in MemoryScope} == {"facts"}
