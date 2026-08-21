"""Which tables Alembic owns, and which it must leave alone.

Four storage systems share one database. Alembic owns the application's own tables;
``AsyncPostgresSaver.setup()`` owns the ``checkpoint*`` tables and ``AsyncPostgresStore.setup()``
owns the ``store*`` tables. Without the filter below, ``alembic revision --autogenerate`` sees
those tables in the database, finds no matching SQLModel, and writes ``op.drop_table(...)``
for each — applying that migration destroys every suspended conversation and every stored
user fact.

Lives here rather than in ``alembic/env.py`` so it can be imported and tested; ``env.py``
runs migrations as a side effect of import and cannot be exercised from a test.
"""

from typing import Any

# Created and migrated by the LangGraph checkpointer.
CHECKPOINTER_TABLES = frozenset(
    {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
)

# Created and migrated by the LangGraph Postgres store (long-term memory).
STORE_TABLES = frozenset({"store", "store_migrations", "store_vectors"})

EXCLUDE_TABLES = CHECKPOINTER_TABLES | STORE_TABLES


def include_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Tell Alembic to ignore tables owned by another system.

    Args:
        obj: The schema object being considered.
        name: Its name in the database.
        type_: The kind of object ("table", "column", "index", …).
        reflected: Whether the object came from database reflection.
        compare_to: The corresponding object on the other side of the comparison.

    Returns:
        bool: False for tables in ``EXCLUDE_TABLES``, True for everything else.
    """
    return not (type_ == "table" and name in EXCLUDE_TABLES)
