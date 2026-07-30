"""Postgres-backed persistence.

Everything in this package opens a database connection: the guideline and
template repositories, the LangGraph checkpointer, and the three run stores
(tracker, history, idempotency).

The run stores lived in `graph/` until 2026-07-30. They import `psycopg_pool`
directly, so an orchestration package was carrying live database access -- the
"psycopg in an orchestration package" smell S1 names. They are adapters, and
they are the same kind of module as the repositories beside them.
"""
