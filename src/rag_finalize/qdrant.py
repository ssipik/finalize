"""Thin Qdrant delete-side client — duplicated from rag_embed by the
standalone-stage convention (this stage only ever removes points; fix bugs in
both copies).

manifest_id names the sighting whose chunks are live, taken from the deletion
row that delta copied off the ledger."""

from __future__ import annotations

from qdrant_client import QdrantClient, models

__all__ = ["QdrantWriter"]


def doc_filter(manifest_id: int) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="manifest_id", match=models.MatchValue(value=manifest_id)
            )
        ]
    )


class QdrantWriter:
    def __init__(self, url: str, collection: str, client: QdrantClient | None = None):
        self.collection = collection
        self._client = client or QdrantClient(url=url)

    def delete_doc_points(self, manifest_id: int) -> None:
        if not self._client.collection_exists(self.collection):
            return  # nothing ever embedded — deletion is a no-op, not an error
        self._client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=doc_filter(manifest_id)),
            wait=True,
        )

    def close(self) -> None:
        self._client.close()
