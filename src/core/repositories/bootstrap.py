"""One-time schema creation for the Fitness Knowledge Store.

Called only from scripts/bootstrap_fitness_db.py (and defensively from repository test
fixtures) -- never from a repository's __init__. Idempotent (IF NOT EXISTS throughout),
safe to re-run.
"""

from psycopg_pool import ConnectionPool

_DDL_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS fitness_kb_sources (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        publisher TEXT,
        url TEXT,
        published_year INTEGER,
        reviewed_at TEXT,
        license TEXT,
        source_type TEXT NOT NULL DEFAULT 'curated_note',
        trust_score DOUBLE PRECISION NOT NULL DEFAULT 0.9,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fitness_kb_documents (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES fitness_kb_sources(id) ON DELETE CASCADE,
        kind TEXT NOT NULL DEFAULT 'guideline',
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        tags TEXT[] NOT NULL DEFAULT '{}',
        goal_applicability TEXT[] NOT NULL DEFAULT '{}',
        equipment_applicability TEXT[] NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS fitness_kb_documents_kind_idx ON fitness_kb_documents (kind)",
    (
        "CREATE INDEX IF NOT EXISTS fitness_kb_documents_source_idx "
        "ON fitness_kb_documents (source_id)"
    ),
    """
    CREATE TABLE IF NOT EXISTS fitness_kb_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES fitness_kb_documents(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        -- Dimension coupled to fitness_kb_embedding_model (text-embedding-3-small).
        -- Changing embedding models later means a destructive column/index rebuild --
        -- this repo has no migration framework, so that's a deliberate, visible
        -- future decision, not hidden here.
        embedding vector(1536),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (document_id, chunk_index)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS fitness_kb_chunks_embedding_idx "
        "ON fitness_kb_chunks USING hnsw (embedding vector_cosine_ops)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS fitness_kb_chunks_document_idx "
        "ON fitness_kb_chunks (document_id)"
    ),
    """
    CREATE TABLE IF NOT EXISTS fitness_kb_templates (
        fingerprint TEXT PRIMARY KEY,
        workout JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
)


def bootstrap_schema(conninfo: str) -> None:
    with ConnectionPool(conninfo, min_size=1, max_size=1, open=True) as pool:
        with pool.connection() as conn:
            for statement in _DDL_STATEMENTS:
                conn.execute(statement)
            conn.commit()
