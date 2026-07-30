#!/usr/bin/env python3
"""One-time schema creation for the Fitness Knowledge Store (Postgres + pgvector).

Run once after `docker compose up -d postgres`, before starting the Fitness MCP
Server or running the ingestion script. Idempotent -- safe to re-run.
"""

from __future__ import annotations

from pathlib import Path

from core.adapters.repositories.bootstrap import bootstrap_schema
from core.config.settings import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    bootstrap_schema(get_settings().checkpointer_dsn)
    print("Fitness knowledge schema ready.")
