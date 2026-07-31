"""Tests for TemplateRepository.

Runs against the real local Postgres instance already used by
core.adapters.db.checkpointer/core.adapters.rate_limit.postgres_store/core.adapters.db.run_tracker in this
dev environment (docker-compose's postgres service). Calls bootstrap_schema()
defensively before constructing the repository, since repositories no longer create
their own schema (see core.adapters.db.bootstrap) -- production trusts
scripts/bootstrap_fitness_db.py has already run; tests can't make that assumption
about a fresh environment, and the call is idempotent/cheap.
"""

from __future__ import annotations

import pytest

from core.adapters.db.bootstrap import bootstrap_schema
from core.adapters.db.template_repository import TemplateRepository
from core.config.settings import get_settings


@pytest.fixture
def template_repository() -> TemplateRepository:
    settings = get_settings()
    bootstrap_schema(settings.checkpointer_dsn)
    repository = TemplateRepository(settings.checkpointer_dsn)
    repository.reset()
    yield repository
    repository.reset()
    repository.close()


def test_get_missing_fingerprint_returns_none(template_repository: TemplateRepository) -> None:
    assert template_repository.get("missing-fingerprint") is None


def test_put_then_get_round_trips_workout(template_repository: TemplateRepository) -> None:
    workout = {"split": "push/pull/legs", "days": [], "weekly_sets": 12}
    template_repository.put("fp-1", workout)
    assert template_repository.get("fp-1") == workout


def test_put_overwrites_existing_fingerprint(template_repository: TemplateRepository) -> None:
    template_repository.put("fp-1", {"weekly_sets": 10})
    template_repository.put("fp-1", {"weekly_sets": 20})
    assert template_repository.get("fp-1") == {"weekly_sets": 20}
