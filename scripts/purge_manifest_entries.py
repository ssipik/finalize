"""Delete documents from ingest_docs, staged_nodes and Qdrant.

    cd finalize
    .venv/bin/python scripts/purge_manifest_entries.py
"""

from __future__ import annotations

from qdrant_client import QdrantClient, models
from sqlalchemy import delete, select

from rag_finalize.db import get_engine, ingest_docs, staged_nodes
from rag_finalize.settings import get_settings
from tables import ingest_manifest

settings = get_settings()
engine = get_engine()


# 1. select the manifest_ids — add criteria here
query = select(ingest_manifest.c.manifest_id)
selection_criteria = [
    ingest_manifest.c.source_id.startswith("bafin_", autoescape=True)
]
for sel in selection_criteria:
    query = query.where(sel)

with engine.connect() as conn:
    manifest_ids = [row[0] for row in conn.execute(query)]

print(f"{len(manifest_ids)} manifest_id(s)")

# 2. delete them from the three stores
client = QdrantClient(url=settings.qdrant_url)
client.delete(
    settings.qdrant_collection,
    points_selector=models.FilterSelector(
        filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="manifest_id", match=models.MatchAny(any=manifest_ids)
                )
            ]
        )
    ),
    wait=True,
)
client.close()

with engine.begin() as conn:
    # 3. delete them from ingest_docs
    ledger = conn.execute(
        delete(ingest_docs).where(ingest_docs.c.manifest_id.in_(manifest_ids))
    ).rowcount
    # 4. delete them from staged_nodes
    staged = conn.execute(
        delete(staged_nodes).where(staged_nodes.c.manifest_id.in_(manifest_ids))
    ).rowcount

print(f"deleted {ledger} ingest_docs row(s), {staged} staged_nodes row(s)")
