"""Postgres+pgvector persistence and retrieval for guideline documents.

Pure SQL, no embedding calls (vectors are always supplied by the caller -- see
core.knowledge.embeddings / core.knowledge.retrieval), no DDL at construction
(schema must already exist -- see core.repositories.bootstrap).

Owns two search channels used by HybridRetriever:
  - search: dense cosine similarity over pgvector embeddings
  - search_keyword: BM25-style lexical ranking via Postgres FTS (ts_rank_cd)
Both accept optional metadata filters (goal / equipment / category). Fusion and
reranking stay outside this class.
"""

from typing import Any

from psycopg_pool import ConnectionPool

from core.knowledge.schema import GuidelineHit, KnowledgeChunk, KnowledgeDocument, KnowledgeSource

_HIT_SELECT = """
    d.id AS document_id, c.id AS chunk_id, d.title, c.content, d.category,
    d.tags, d.goal_applicability, d.equipment_applicability,
    s.url AS source_url, s.source_type, s.trust_score
"""


def _format_vector(vector: list[float]) -> str:
    return "[" + ",".join(str(value) for value in vector) + "]"


def _metadata_filter_sql(*, goal_key: str, equipment_key: str, category_key: str) -> str:
    """Documents with empty applicability arrays match any filter (universal notes).

    Parameters are cast to text so psycopg can bind NULL without AmbiguousParameter.
    """
    return f"""
      AND (
            %({goal_key})s::text IS NULL
            OR cardinality(d.goal_applicability) = 0
            OR %({goal_key})s::text = ANY(d.goal_applicability)
          )
      AND (
            %({equipment_key})s::text IS NULL
            OR cardinality(d.equipment_applicability) = 0
            OR %({equipment_key})s::text = ANY(d.equipment_applicability)
          )
      AND (
            %({category_key})s::text IS NULL
            OR d.category = %({category_key})s::text
          )
    """


def _normalize_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _row_to_hit(row: tuple[Any, ...]) -> GuidelineHit:
    return GuidelineHit(
        document_id=row[0],
        chunk_id=row[1],
        title=row[2],
        content=row[3],
        category=row[4],
        tags=list(row[5]),
        goal_applicability=list(row[6]),
        equipment_applicability=list(row[7]),
        source_url=row[8],
        source_type=row[9],
        trust_score=row[10],
        similarity=float(row[11]),
    )


class GuidelineRepository:
    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        self._pool = ConnectionPool(
            conninfo,
            min_size=min_size,
            max_size=max_size,
            timeout=connect_timeout_seconds,
            open=True,
        )

    def upsert(
        self,
        source: KnowledgeSource,
        document: KnowledgeDocument,
        chunks_with_vectors: list[tuple[KnowledgeChunk, list[float]]],
    ) -> None:
        """Upserts source, document, and all chunk rows in one transaction. Deletes any
        chunk rows for this document_id whose chunk_index falls outside the new set
        first -- without this, re-ingesting a document that now produces fewer chunks
        than before leaves orphaned stale rows that stay permanently searchable."""
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO fitness_kb_sources
                    (id, title, publisher, url, published_year, reviewed_at, license,
                     source_type, trust_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    publisher = EXCLUDED.publisher,
                    url = EXCLUDED.url,
                    published_year = EXCLUDED.published_year,
                    reviewed_at = EXCLUDED.reviewed_at,
                    license = EXCLUDED.license,
                    source_type = EXCLUDED.source_type,
                    trust_score = EXCLUDED.trust_score
                """,
                (
                    source.id,
                    source.title,
                    source.publisher,
                    source.url,
                    source.published_year,
                    source.reviewed_at,
                    source.license,
                    source.source_type,
                    source.trust_score,
                ),
            )
            conn.execute(
                """
                INSERT INTO fitness_kb_documents
                    (id, source_id, kind, title, category, tags, goal_applicability,
                     equipment_applicability, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    kind = EXCLUDED.kind,
                    title = EXCLUDED.title,
                    category = EXCLUDED.category,
                    tags = EXCLUDED.tags,
                    goal_applicability = EXCLUDED.goal_applicability,
                    equipment_applicability = EXCLUDED.equipment_applicability,
                    updated_at = now()
                """,
                (
                    document.id,
                    document.source_id,
                    document.kind,
                    document.title,
                    document.category,
                    document.tags,
                    document.goal_applicability,
                    document.equipment_applicability,
                ),
            )
            conn.execute(
                "DELETE FROM fitness_kb_chunks WHERE document_id = %s AND chunk_index >= %s",
                (document.id, len(chunks_with_vectors)),
            )
            for chunk, vector in chunks_with_vectors:
                conn.execute(
                    """
                    INSERT INTO fitness_kb_chunks (id, document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                    """,
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.content,
                        _format_vector(vector),
                    ),
                )
            conn.commit()

    def search(
        self,
        *,
        kind: str,
        query_embedding: list[float],
        limit: int,
        min_similarity: float,
        goal: str | None = None,
        equipment: str | None = None,
        category: str | None = None,
    ) -> list[GuidelineHit]:
        """Dense cosine search. Optional metadata filters narrow the candidate set
        before ranking so goal/equipment mismatches do not crowd the top-k."""
        vector_literal = _format_vector(query_embedding)
        params: dict[str, Any] = {
            "query_vec": vector_literal,
            "kind": kind,
            "min_similarity": min_similarity,
            "limit": limit,
            "goal": _normalize_filter(goal),
            "equipment": _normalize_filter(equipment),
            "category": _normalize_filter(category),
        }
        metadata_sql = _metadata_filter_sql(
            goal_key="goal", equipment_key="equipment", category_key="category"
        )
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT DISTINCT ON (d.id)
                        {_HIT_SELECT},
                        1 - (c.embedding <=> %(query_vec)s::vector) AS similarity
                    FROM fitness_kb_chunks c
                    JOIN fitness_kb_documents d ON d.id = c.document_id
                    JOIN fitness_kb_sources s ON s.id = d.source_id
                    WHERE d.kind = %(kind)s
                      AND 1 - (c.embedding <=> %(query_vec)s::vector) >= %(min_similarity)s
                      {metadata_sql}
                    ORDER BY d.id, similarity DESC
                ) AS best_chunk_per_document
                ORDER BY similarity DESC
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        return [_row_to_hit(row) for row in rows]

    def search_keyword(
        self,
        *,
        kind: str,
        query: str,
        limit: int,
        goal: str | None = None,
        equipment: str | None = None,
        category: str | None = None,
    ) -> list[GuidelineHit]:
        """Lexical / BM25-style channel using Postgres full-text search.

        ``ts_rank_cd`` approximates BM25-like term weighting without a separate
        search engine. Empty or unparseable queries return no hits. Similarity on
        the hit is the FTS rank so RRF can still prefer stronger lexical matches
        when choosing the payload for a fused chunk id.
        """
        cleaned = query.strip()
        if not cleaned or limit <= 0:
            return []
        params: dict[str, Any] = {
            "kind": kind,
            "query": cleaned,
            "limit": limit,
            "goal": _normalize_filter(goal),
            "equipment": _normalize_filter(equipment),
            "category": _normalize_filter(category),
        }
        metadata_sql = _metadata_filter_sql(
            goal_key="goal", equipment_key="equipment", category_key="category"
        )
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT DISTINCT ON (d.id)
                        {_HIT_SELECT},
                        ts_rank_cd(
                            to_tsvector('english', c.content),
                            plainto_tsquery('english', %(query)s)
                        ) AS similarity
                    FROM fitness_kb_chunks c
                    JOIN fitness_kb_documents d ON d.id = c.document_id
                    JOIN fitness_kb_sources s ON s.id = d.source_id
                    WHERE d.kind = %(kind)s
                      AND to_tsvector('english', c.content)
                          @@ plainto_tsquery('english', %(query)s)
                      {metadata_sql}
                    ORDER BY d.id, similarity DESC
                ) AS best_chunk_per_document
                ORDER BY similarity DESC
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        return [_row_to_hit(row) for row in rows]

    def reset(self) -> None:
        """Clear all rows -- used in tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE fitness_kb_chunks, fitness_kb_documents, fitness_kb_sources")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
