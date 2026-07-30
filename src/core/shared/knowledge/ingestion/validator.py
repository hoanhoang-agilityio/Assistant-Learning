"""Splits a raw loader record into (Source, Document, content) for the Chunker.

For today's flat JSONL rows: source.id = document.id = record["id"], source.title =
document.title = record["title"], content = record["content"]. A future richer loader
(e.g. one Source with many Documents) would produce distinct ids naturally -- this
function's contract (return one Source + one Document + content per record) is what
future loaders must satisfy, not what they're limited to internally.
"""

from core.shared.knowledge.ingestion.loader import RawKnowledgeRecord
from core.shared.knowledge.schema import KnowledgeDocument, KnowledgeSource


def validate_record(record: RawKnowledgeRecord) -> tuple[KnowledgeSource, KnowledgeDocument, str]:
    source = KnowledgeSource(
        id=record["id"],
        title=record["title"],
        url=record.get("source_url"),
        published_year=record.get("published_year"),
        reviewed_at=record.get("reviewed_at"),
        source_type=record.get("source_type", "curated_note"),
        trust_score=record.get("trust_score", 0.9),
    )
    document = KnowledgeDocument(
        id=record["id"],
        source_id=source.id,
        kind=record.get("kind", "guideline"),
        title=record["title"],
        category=record["category"],
        tags=record.get("tags", []),
        goal_applicability=record.get("goal_applicability", []),
        equipment_applicability=record.get("equipment_applicability", []),
    )
    return source, document, record["content"]
