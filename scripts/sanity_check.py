"""Sanity check for one batch: Postgres ledger vs Qdrant.

Run after `python -m rag_embed --batch-id <id>` (or after this stage, to see
deletions reflected) against the same ../postgres and ../qdrant.

    cd finalize
    .venv/bin/python scripts/sanity_check.py --batch-id <id>

Omit --batch-id to list recent batches (id, run, doc counts per status) and exit.

Exit code 0 if every check passes, 1 otherwise.

Scope:
- Checks 1-4 are batch-scoped (this batch's manifest_ids only).
- Checks 5-6 are GLOBAL (the whole Qdrant collection vs the whole active
  ledger), because orphan/missing points are a store-wide property.

Notes on what the checks assume:
- skipped_unchanged docs DO land in ingest_docs — the ledger write is by design,
  so delta stops re-triggering them.
- skipped_empty docs (no text) land in ingest_docs with status 'empty' and have
  no points, so the active-only checks 5-6 leave them out.
- ingest_docs is one row per document; Qdrant is one point per chunk, so the
  counts are compared as distinct manifest_ids, not raw point count.
"""

from __future__ import annotations

import argparse
import sys

from qdrant_client import QdrantClient
from sqlalchemy import func, select

from rag_finalize.db import get_engine, ingest_batch_docs, ingest_batches, ingest_docs
from rag_finalize.settings import get_settings

# statuses a batch doc can hold after a clean embed run
DONE_STATUSES = {"embedded", "skipped_unchanged", "skipped_empty"}


class Report:
    def __init__(self) -> None:
        self.failed = False

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        tag = "PASS" if passed else "FAIL"
        if not passed:
            self.failed = True
        line = f"[{tag}] {name}"
        if detail:
            line += f"\n       {detail}"
        print(line)

    def info(self, name: str, detail: str) -> None:
        print(f"[INFO] {name}\n       {detail}")


def qdrant_manifest_ids(client: QdrantClient, collection: str) -> set[int]:
    """Distinct manifest_ids present in the collection, read from the point
    payloads (the same key this stage deletes by)."""
    ids: set[int] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=["manifest_id"],
            with_vectors=False,
        )
        for p in points:
            mid = (p.payload or {}).get("manifest_id")
            if isinstance(mid, int):
                ids.add(mid)
        if offset is None:
            break
    return ids


def list_batches(engine, limit: int = 20) -> int:
    """Print recent batches with per-status doc counts; a menu for --batch-id."""
    with engine.connect() as conn:
        batches = [
            dict(r)
            for r in conn.execute(
                select(ingest_batches).order_by(ingest_batches.c.batch_id.desc()).limit(limit)
            ).mappings()
        ]
        if not batches:
            print("no batches in ingest_batches — did plan run?")
            return 0
        status_counts = {
            (r["batch_id"], r["status"]): r["n"]
            for r in conn.execute(
                select(
                    ingest_batch_docs.c.batch_id,
                    ingest_batch_docs.c.status,
                    func.count().label("n"),
                )
                .where(ingest_batch_docs.c.batch_id.in_([b["batch_id"] for b in batches]))
                .group_by(ingest_batch_docs.c.batch_id, ingest_batch_docs.c.status)
            ).mappings()
        }
    print(f"{'batch_id':>10}  {'run_id':<16} {'docs':>5}  status breakdown")
    for b in batches:
        bid = b["batch_id"]
        breakdown = ", ".join(
            f"{st}={n}"
            for (bb, st), n in sorted(status_counts.items())
            if bb == bid
        ) or "(no docs)"
        print(f"{bid:>10}  {b['run_id']:<16} {b['doc_count']:>5}  {breakdown}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-id", type=int, help="batch to check; omit to list batches")
    args = ap.parse_args()

    settings = get_settings()
    engine = get_engine()

    if args.batch_id is None:
        return list_batches(engine)
    batch_id = args.batch_id
    rep = Report()

    with engine.connect() as conn:
        batch_rows = [
            dict(r)
            for r in conn.execute(
                select(
                    ingest_batch_docs.c.manifest_id,
                    ingest_batch_docs.c.status,
                ).where(ingest_batch_docs.c.batch_id == batch_id)
            ).mappings()
        ]
        if not batch_rows:
            print(f"no rows in ingest_batch_docs for batch {batch_id} — bad id?")
            return 1

        batch_ids = {r["manifest_id"] for r in batch_rows}
        embedded_ids = {r["manifest_id"] for r in batch_rows if r["status"] == "embedded"}
        skipped_ids = {
            r["manifest_id"] for r in batch_rows if r["status"] == "skipped_unchanged"
        }
        # docs that parsed to no text: a ledger row (status 'empty'), no points
        empty_ids = {
            r["manifest_id"] for r in batch_rows if r["status"] == "skipped_empty"
        }
        other = {
            r["manifest_id"]: r["status"]
            for r in batch_rows
            if r["status"] not in DONE_STATUSES
        }

        # ledger rows for this batch's sightings (manifest_id was moved onto the
        # new sighting by embed, so it equals the batch doc's manifest_id)
        ledger_batch_ids = {
            r["manifest_id"]
            for r in conn.execute(
                select(ingest_docs.c.manifest_id).where(
                    ingest_docs.c.manifest_id.in_(batch_ids)
                )
            ).mappings()
        }
        # whole active ledger, for the global Qdrant checks
        active_ledger_ids = {
            r["manifest_id"]
            for r in conn.execute(
                select(ingest_docs.c.manifest_id).where(ingest_docs.c.status == "active")
            ).mappings()
        }
        global_ledger_count = conn.execute(
            select(func.count()).select_from(ingest_docs)
        ).scalar_one()

    print(f"=== sanity check: batch {batch_id} "
          f"({len(batch_rows)} batch docs) ===\n")

    # 1. every batch doc reached a terminal embed status
    rep.check(
        "1. all batch docs are 'embedded', 'skipped_unchanged' or 'skipped_empty'",
        not other,
        "" if not other
        else f"{len(other)} not terminal: "
             + ", ".join(f"{mid}={st}" for mid, st in list(other.items())[:10]),
    )

    # 2. embedded docs are in the ledger
    missing_embedded = embedded_ids - ledger_batch_ids
    rep.check(
        f"2. all 'embedded' docs appear in ingest_docs ({len(embedded_ids)} embedded)",
        not missing_embedded,
        "" if not missing_embedded else f"missing: {sorted(missing_embedded)[:10]}",
    )

    # 3. skipped_unchanged docs are in the ledger too — embed writes a ledger
    #    row for them so delta stops re-triggering them.
    missing_skipped = skipped_ids - ledger_batch_ids
    rep.check(
        f"3. all 'skipped_unchanged' docs appear in ingest_docs "
        f"({len(skipped_ids)} skipped)",
        not missing_skipped,
        "" if not missing_skipped else f"missing: {sorted(missing_skipped)[:10]}",
    )

    # 4. batch-scoped ledger count == terminal batch docs
    expected = len(embedded_ids) + len(skipped_ids) + len(empty_ids)
    rep.check(
        "4. ingest_docs rows for this batch == embedded+skipped+empty batch docs",
        len(ledger_batch_ids) == expected,
        f"ledger(batch)={len(ledger_batch_ids)} vs "
        f"embedded+skipped+empty={expected} (empty={len(empty_ids)})",
    )
    rep.info("    global ingest_docs row count", str(global_ledger_count))

    # ---- Qdrant (global) ----
    client = QdrantClient(url=settings.qdrant_url)
    collection = settings.qdrant_collection
    if not client.collection_exists(collection):
        rep.check(f"5-6. Qdrant collection '{collection}' exists", False,
                  "collection missing — did embed run against this Qdrant?")
        print()
        return 1

    points_count = client.count(collection, exact=True).count
    qdrant_ids = qdrant_manifest_ids(client, collection)
    rep.info("    Qdrant raw points_count (1 per chunk)", str(points_count))

    # 5. distinct manifest_ids in Qdrant == active ledger rows (1 doc = many
    #    points, so the raw point count is not comparable)
    rep.check(
        "5. distinct manifest_ids in Qdrant == active ingest_docs rows",
        len(qdrant_ids) == len(active_ledger_ids),
        f"qdrant distinct docs={len(qdrant_ids)} vs active ledger={len(active_ledger_ids)}",
    )

    # 6. every active ledger doc has >=1 point in Qdrant; flag orphans too
    missing_in_qdrant = active_ledger_ids - qdrant_ids
    orphan_in_qdrant = qdrant_ids - active_ledger_ids
    rep.check(
        "6. every active ingest_docs manifest_id is represented in Qdrant",
        not missing_in_qdrant,
        "" if not missing_in_qdrant
        else f"{len(missing_in_qdrant)} ledger docs with no points: "
             f"{sorted(missing_in_qdrant)[:10]}",
    )
    if orphan_in_qdrant:
        rep.info(
            "    Qdrant manifest_ids with no active ledger row (orphans/stale)",
            f"{len(orphan_in_qdrant)}: {sorted(orphan_in_qdrant)[:10]}",
        )

    print()
    print("RESULT:", "FAIL" if rep.failed else "OK")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
