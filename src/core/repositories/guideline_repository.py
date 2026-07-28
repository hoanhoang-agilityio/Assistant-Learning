"""Postgres+pgvector persistence and retrieval for guideline documents.

Pure SQL, no embedding calls (vectors are always supplied by the caller -- see
core.knowledge.embeddings / core.knowledge.retrieval_service), no DDL at construction
(schema must already exist -- see core.repositories.bootstrap).
"""

from typing import Any

from psycopg_pool import ConnectionPool

from core.knowledge.schema import GuidelineHit, KnowledgeChunk, KnowledgeDocument, KnowledgeSource


def _format_vector(vector: list[float]) -> str:
    return "[" + ",".join(str(value) for value in vector) + "]"


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
    ) -> list[GuidelineHit]:
        """JOIN chunks -> documents -> sources, filter by kind + cosine-similarity floor,
        dedupe to the best-scoring chunk per document, return the top `limit` documents
        by similarity. Takes a ready-made vector -- never embeds text itself.

        DISTINCT ON requires its leading ORDER BY expressions to match (d.id here), so
        the dedupe pass is a subquery: the inner query collapses to one row per document
        (best chunk), the outer query re-sorts by similarity and applies LIMIT -- doing
        both in one ORDER BY would apply LIMIT to rows ordered by document id, not by
        relevance.
        """
        vector_literal = _format_vector(query_embedding)
        params: dict[str, Any] = {
            "query_vec": vector_literal,
            "kind": kind,
            "min_similarity": min_similarity,
            "limit": limit,
        }
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT DISTINCT ON (d.id)
                        d.id AS document_id, c.id AS chunk_id, d.title, c.content, d.category,
                        d.tags, d.goal_applicability, d.equipment_applicability,
                        s.url AS source_url, s.source_type, s.trust_score,
                        1 - (c.embedding <=> %(query_vec)s::vector) AS similarity
                    FROM fitness_kb_chunks c
                    JOIN fitness_kb_documents d ON d.id = c.document_id
                    JOIN fitness_kb_sources s ON s.id = d.source_id
                    WHERE d.kind = %(kind)s
                      AND 1 - (c.embedding <=> %(query_vec)s::vector) >= %(min_similarity)s
                    ORDER BY d.id, similarity DESC
                ) AS best_chunk_per_document
                ORDER BY similarity DESC
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        return [
            GuidelineHit(
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
                similarity=row[11],
            )
            for row in rows
        ]

    def reset(self) -> None:
        """Clear all rows -- used in tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE fitness_kb_chunks, fitness_kb_documents, fitness_kb_sources")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
