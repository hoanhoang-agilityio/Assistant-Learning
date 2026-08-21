-- Runs once, on first container start, before Alembic or the checkpointer ever connect.
-- pgvector must exist before any migration that declares a vector column.
CREATE EXTENSION IF NOT EXISTS vector;
