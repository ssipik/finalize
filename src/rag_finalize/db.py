from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from rag_finalize.settings import get_settings

metadata = MetaData()

# Mirrors ../postgres/sql/002_delta.sql. Write side here is the tombstone
# only: finalize flips status active → deleted (rows are kept so a later
# re-listing classifies as 'reappeared', never dropped).
ingest_docs = Table(
    "ingest_docs",
    metadata,
    # the sighting whose points are live in Qdrant
    Column("manifest_id", BigInteger, primary_key=True),
    Column("text_sha", Text),
    Column("parser_version", Text),
    Column("status", Text, nullable=False),
)

ingest_deletions = Table(
    "ingest_deletions",
    metadata,
    Column("manifest_id", BigInteger, primary_key=True),
    # the run that DETECTED the deletion, not the sighting's run
    Column("run_id", Text, nullable=False),
)

# Mirrors ../postgres/sql/003_plan.sql — read side (quality gate + cleanup scope).
ingest_batches = Table(
    "ingest_batches",
    metadata,
    # GENERATED ALWAYS AS IDENTITY in the DDL: plan gets it via RETURNING.
    Column("batch_id", BigInteger, primary_key=True),
    # the run the batch was PLANNED in, not its docs' sighting runs
    Column("run_id", Text, nullable=False),
    Column("doc_count", Integer, nullable=False),
    Column("planned_cost", BigInteger, nullable=False),
)

ingest_batch_docs = Table(
    "ingest_batch_docs",
    metadata,
    # PK is (batch_id, manifest_id): plan is append-only, so a re-listed doc
    # gets a new row on the new batch and earlier batches keep theirs. Every
    # writer must filter on BOTH (see 003_plan.sql).
    Column("manifest_id", BigInteger, primary_key=True),
    Column("batch_id", BigInteger, primary_key=True),
    Column("cost", BigInteger, nullable=False),
    Column("status", Text, nullable=False),
    Column("error", Text),
    Column("content_sha", Text),
    Column("text_sha", Text),
    Column("parser_version", Text),
    Column("node_count", Integer),
    # what the parser could read: pages, chars_per_page, image_coverage,
    # low_text (the parse_chunk stage writes it; see 004_parse_chunk.sql).
    # none_as_null: a Python None must land as SQL NULL, not JSON 'null'.
    Column("parse_quality", JSONB(none_as_null=True)),
)

# Mirrors ../postgres/sql/004_parse_chunk.sql — finalize deletes the rows of
# done batches (the "transient" guarantee of the vector store).
staged_nodes = Table(
    "staged_nodes",
    metadata,
    Column("manifest_id", BigInteger, primary_key=True),
    Column("node_seq", Integer, primary_key=True),
    Column("batch_id", BigInteger, nullable=False),
    Column("text", Text, nullable=False),
    Column("metadata", JSONB, nullable=False),
)


def get_engine(dsn: str | None = None) -> Engine:
    return create_engine(dsn or get_settings().pg_dsn)
