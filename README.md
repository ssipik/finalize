# rag-finalize

Stage 6 (FINALIZE) of the RAG ingestion pipeline — see [`../ARCHITECTURE.md`](../ARCHITECTURE.md) (block 11). Closes an ingestion run, in this order:

1. **Quality gate** — raises `QualityGateError` (fails the DAG loudly, exit 1) when the parse-error rate over the run's batch docs exceeds `RAG_MAX_PARSE_ERROR_RATE` (default 20 %) — *before* touching Qdrant or the ledger, so a source-site redesign never silently poisons the index.
2. **Apply deletions** — for each `ingest_deletions` row whose ledger doc is still `active`: remove the doc's Qdrant points, tombstone the ledger row (`status='deleted'` — kept so a later re-listing classifies as *reappeared*). The active-only filter makes re-runs idempotent without deletion-state bookkeeping.
3. **Clear staging** — delete `staged_nodes` of `done` batches (block 6: chunk text in Postgres is transient); unfinished batches keep theirs and are reported.

## Usage

```bash
uv sync --frozen --extra dev        # lock-exact venv from uv.lock
.venv/bin/python -m pytest          # offline tests (pure gate/deletion logic)

# Finalize one plan run (needs ../postgres + ../qdrant up)
python -m rag_finalize --run-id <run_id>

# Whole-table: all batches, every still-active deletion
python -m rag_finalize

# Containerized
docker compose run --rm --build pipeline python -m rag_finalize --run-id <id>
```

## Design notes

- Later additions per block 11: metrics → Langfuse, optional `TriggerDagRun` of the eval DAG — both land with block 12.
- Standalone module by convention: infrastructure (`settings.py`, `sources.py`, `db.py`, `qdrant.py`) duplicated from the other stages, dedup deferred.
