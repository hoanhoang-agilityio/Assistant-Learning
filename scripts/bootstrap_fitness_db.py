#!/usr/bin/env python3
"""One-time schema creation for the Fitness Knowledge Store (Postgres + pgvector).

Run once after `docker compose up -d postgres`, before starting the Fitness MCP
Server or running the ingestion script. Idempotent -- safe to re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from core.config.settings import get_settings  # noqa: E402
from core.repositories.bootstrap import bootstrap_schema  # noqa: E402

if __name__ == "__main__":
    bootstrap_schema(get_settings().checkpointer_dsn)
    print("Fitness knowledge schema ready.")
