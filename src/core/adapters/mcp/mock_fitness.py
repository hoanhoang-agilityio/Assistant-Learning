"""Deterministic dev/test doubles for the Fitness MCP client.

build_mock_fitness_client(): used when MOCK_FITNESS_KB=true (local dev without a
running Fitness MCP Server/Postgres) -- mirrors core.adapters.mcp.mock_tavily's shape.

build_fake_fitness_client(): used by tests/conftest.py's `fitness_client` fixture --
needs real in-memory state since template put/get must round-trip within a test
(unlike Tavily's stateless canned responses).
"""

from __future__ import annotations

from typing import Any

from core.adapters.mcp.fitness_client import FitnessMCPClient

_MOCK_GUIDELINE: dict[str, Any] = {
    "document_id": "mock-guideline",
    "chunk_id": "mock-guideline::0",
    "title": "Evidence-based training and nutrition guidance",
    "content": (
        "Resistance training with hypertrophy and strength work supports macro targets, "
        "caloric deficit planning, protein intake, recovery, and weekly training volume."
    ),
    "category": "general",
    "tags": ["training", "nutrition"],
    "goal_applicability": ["fat_loss", "muscle_gain", "recomposition", "general_fitness"],
    "equipment_applicability": ["gym", "home", "bodyweight"],
    "source_url": "local-kb://mock-guideline",
    "source_type": "guideline",
    "trust_score": 0.9,
    "similarity": 0.9,
}


def build_mock_fitness_client() -> FitnessMCPClient:
    """Deterministic Fitness MCP responses for local dev (MOCK_FITNESS_KB=true)."""
    templates: dict[str, dict[str, Any]] = {}

    def search_guidelines(**_kwargs: Any) -> dict[str, Any]:
        return {"documents": [_MOCK_GUIDELINE], "sufficient_coverage": True}

    def search_training_template(fingerprint: str) -> dict[str, Any]:
        return {"workout": templates.get(fingerprint)}

    def store_training_template(fingerprint: str, workout: dict[str, Any]) -> dict[str, Any]:
        templates[fingerprint] = workout
        return {"stored": True}

    return FitnessMCPClient(
        search_guidelines=search_guidelines,
        search_training_template=search_training_template,
        store_training_template=store_training_template,
    )


def build_fake_fitness_client(documents: list[dict[str, Any]] | None = None) -> FitnessMCPClient:
    """In-memory test double -- injected via tests/conftest.py's `fitness_client` fixture."""
    templates: dict[str, dict[str, Any]] = {}
    docs = documents or []

    def store_training_template(fingerprint: str, workout: dict[str, Any]) -> dict[str, Any]:
        templates[fingerprint] = workout
        return {"stored": True}

    return FitnessMCPClient(
        search_guidelines=lambda **_kwargs: {
            "documents": docs,
            "sufficient_coverage": bool(docs),
        },
        search_training_template=lambda fingerprint: {"workout": templates.get(fingerprint)},
        store_training_template=store_training_template,
    )
