from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine

from rag_finalize.db import (
    get_engine,
    ingest_batch_docs,
    ingest_batches,
    ingest_deletions,
    ingest_docs,
    staged_nodes,
)
from rag_finalize.qdrant import QdrantWriter
from rag_finalize.settings import get_settings

logger = logging.getLogger(__name__)


class QualityGateError(RuntimeError):
    """Parse-error rate over threshold — the DAG must fail loudly, because a
    BaFin site redesign must not silently poison the index."""


@dataclass
class FinalizeReport:
    run_id: str
    doc_counts: dict[str, int] = field(default_factory=dict)
    error_rate: float = 0.0
    deletions_applied: int = 0
    staged_rows_deleted: int = 0
    unfinished_batches: int = 0


def parse_error_rate(doc_statuses: list[str]) -> float:
    """Share of batch docs whose parse ultimately failed. Docs re-planned
    later overwrite their row (same identity), so this reflects current
    state, not accumulated history."""
    if not doc_statuses:
        return 0.0
    return doc_statuses.count("error") / len(doc_statuses)


def select_applicable_deletions(
    deletion_rows: list[dict], ledger_by_id: dict[int, dict]
) -> list[dict]:
    """Deletions worth applying: the ledger row still exists and is active.

    This is what makes re-running finalize idempotent without deletion-state
    bookkeeping — already-tombstoned (or never-ingested) docs drop out. Keying
    on manifest_id also drops a stale row for a document that has since
    reappeared: re-ingesting moved the ledger onto a newer sighting, so the
    old deletion row matches nothing."""
    return [
        row
        for row in deletion_rows
        if (ledger := ledger_by_id.get(row["manifest_id"])) is not None
        and ledger["status"] == "active"
    ]


def run_finalize(
    run_id: str,
    engine: Engine | None = None,
    writer: QdrantWriter | None = None,
) -> FinalizeReport:
    """FINALIZE stage: quality gate → apply deletions → clear staging.

    Always scoped to one run — that run's batches (ingest_batches.run_id) and
    its deletions. A whole-corpus cycle is a run too, under its own
    all-<timestamp> run_id.

    Order matters: the gate raises QualityGateError BEFORE anything is
    applied, so a poisoned run changes neither Qdrant nor the ledger.
    Deletions remove the doc's points and tombstone the ledger row
    (status='deleted' — kept so a re-listing classifies as 'reappeared').
    Staged nodes of 'done' batches are deleted (the vector store: transient);
    unfinished batches keep theirs and are reported.
    """
    if not run_id:
        raise ValueError("run_id is required")
    settings = get_settings()
    engine = engine or get_engine()

    with engine.connect() as conn:
        batches = [
            dict(r)
            for r in conn.execute(
                select(ingest_batches).where(ingest_batches.c.run_id == run_id)
            ).mappings()
        ]
        batch_ids = [b["batch_id"] for b in batches]
        batch_docs = (
            [
                dict(r)
                for r in conn.execute(
                    select(ingest_batch_docs).where(
                        ingest_batch_docs.c.batch_id.in_(batch_ids)
                    )
                ).mappings()
            ]
            if batch_ids
            else []
        )
        deletion_docs = [
            dict(r)
            for r in conn.execute(
                select(ingest_deletions).where(ingest_deletions.c.run_id == run_id)
            ).mappings()
        ]
        deletion_docs_ids = {d["manifest_id"] for d in deletion_docs}
        # Filtered in Postgres: only the ledger rows for the batch_docs being
        # deleted, not the whole ledger.
        ledger_docs = {
            l["manifest_id"]: dict(l)
            for l in conn.execute(
                select(ingest_docs).where(ingest_docs.c.manifest_id.in_(deletion_docs_ids))
            ).mappings()
        }

    report = FinalizeReport(run_id=run_id)
    for doc in batch_docs:
        report.doc_counts[doc["status"]] = report.doc_counts.get(doc["status"], 0) + 1
    report.error_rate = parse_error_rate([d["status"] for d in batch_docs])
    # No batch-status column: a batch is unfinished iff any of its batch_docs is
    # still 'pending' or 'staged' (parse/embed not yet through it). A batch
    # with no such batch_docs — including an empty batch — counts as done.
    unfinished_batch_ids = {
        d["batch_id"] for d in batch_docs if d["status"] in ("pending", "staged")
    }
    report.unfinished_batches = sum(
        1 for b in batches if b["batch_id"] in unfinished_batch_ids
    )

    if report.error_rate > settings.max_parse_error_rate:
        raise QualityGateError(
            f"parse-error rate {report.error_rate:.1%} exceeds threshold "
            f"{settings.max_parse_error_rate:.1%} "
            f"({report.doc_counts.get('error', 0)} of {len(batch_docs)} batch_docs) — "
            "failing before applying deletions"
        )

    to_apply = select_applicable_deletions(deletion_docs, ledger_docs)
    own_writer = writer is None
    if to_apply:
        writer = writer or QdrantWriter(
            settings.qdrant_url, settings.qdrant_collection, settings.http_timeout
        )
        try:
            for row in to_apply:
                writer.delete_doc_points(row["manifest_id"])
                with engine.begin() as conn:
                    conn.execute(
                        update(ingest_docs)
                        .where(ingest_docs.c.manifest_id == row["manifest_id"])
                        .values(status="deleted")
                    )
                report.deletions_applied += 1
        finally:
            if own_writer:
                writer.close()

    done_batch_ids = [
        b["batch_id"] for b in batches if b["batch_id"] not in unfinished_batch_ids
    ]
    if done_batch_ids:
        with engine.begin() as conn:
            result = conn.execute(
                delete(staged_nodes).where(staged_nodes.c.batch_id.in_(done_batch_ids))
            )
            report.staged_rows_deleted = result.rowcount
    logger.info(
        "finalize %s: batch_docs=%s error_rate=%.1f%% deletions=%d staged_deleted=%d unfinished=%d",
        report.run_id,
        report.doc_counts,
        report.error_rate * 100,
        report.deletions_applied,
        report.staged_rows_deleted,
        report.unfinished_batches,
    )
    return report
