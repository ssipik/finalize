"""Read-side mirror of ../../postgres/sql/001_discover.sql for the ops scripts.

Only ingest_manifest lives here: the finalize stage never reads it, so it is not
in rag_finalize.db, but the purge script needs it to resolve criteria to
manifest_ids. ingest_docs and staged_nodes come from rag_finalize.db.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

ingest_manifest = Table(
    "ingest_manifest",
    metadata,
    Column("manifest_id", BigInteger, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("source_system", Text, nullable=False),
    Column("doc_url", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("title", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("doc_version", Text),
    Column("size_bytes", BigInteger),
    Column("extra", JSONB, nullable=False),
    Column("execution_ts", DateTime(timezone=True), nullable=False),
)
