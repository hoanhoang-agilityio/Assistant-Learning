"""Alembic environment.

Imports ``app.models`` for its side effect: SQLModel only registers a table in
``SQLModel.metadata`` when the module defining it is imported, and autogenerate
reads that metadata. Skip the import and every migration comes out empty.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (populates SQLModel.metadata)
from alembic import context
from app.core.configs.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# One source of truth for the URL: whatever the app connects to, Alembic migrates.
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)

target_metadata = SQLModel.metadata

# Tables created and migrated by systems other than Alembic: the LangGraph
# AsyncPostgresSaver (via checkpointer.setup()) and mem0's pgvector store. They
# have no SQLModel counterpart, so without this filter the first autogenerate
# run after the checkpointer exists emits op.drop_table("checkpoints") — and
# applying that deletes every conversation.
EXCLUDE_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
    "longterm_memory",
    "mem0migrations",
}


# Indexes declared by hand in a migration because autogenerate cannot express
# them. GIN indexes on text[] columns are the case here: Alembic does not read
# an existing index's access method, so an index created `USING gin` looks like
# one it never created, and every later autogenerate proposes dropping it.
# Applying that turns the catalog's array containment queries into sequential
# scans, silently. The HNSW index on `knowledge_chunks.embedding` carries an
# operator class as well, which autogenerate cannot express either.
EXCLUDE_INDEX_SUFFIXES = ("_gin", "_hnsw")


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Skip schema objects Alembic does not own or cannot represent.

    Args:
        obj: The reflected or metadata schema object.
        name: Object name as it appears in the database.
        type_: Object kind, e.g. ``"table"``, ``"column"`` or ``"index"``.
        reflected: Whether the object came from database reflection.
        compare_to: The counterpart object being diffed against, if any.

    Returns:
        ``False`` for tables in ``EXCLUDE_TABLES`` and hand-written indexes,
        ``True`` otherwise.
    """
    if type_ == "index" and name and name.endswith(EXCLUDE_INDEX_SUFFIXES):
        return False
    return not (type_ == "table" and name in EXCLUDE_TABLES)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against the live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
            # SQLite cannot ALTER most things in place; batch mode rewrites the
            # table instead, so the same migration works on both backends.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
