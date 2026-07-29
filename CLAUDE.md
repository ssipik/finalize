# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Stage 6 (FINALIZE) of the six-stage ingestion skeleton — `../ARCHITECTURE.md` block 11 is authoritative. Standalone stage module: `settings.py`, `sources.py`, `db.py`, `qdrant.py` are **deliberately duplicated** from the other stage packages — fix infra bugs in every copy.

## Commands

```bash
uv sync --frozen --extra dev              # lock-exact venv
.venv/bin/python -m pytest                # offline tests (pure gate/deletion logic)
python -m rag_finalize --run-id <id>      # finalize a plan run (needs ../postgres + ../qdrant)
python -m rag_finalize                    # whole-table mode
```

## Invariants

- **Library-first, thin `__main__`**: stage logic in `rag_finalize.finalize.run_finalize()`; `__main__.py` is a logic-free argparse wrapper.
- **Gate before side effects**: `QualityGateError` must fire before any Qdrant delete or ledger write — a poisoned run changes nothing. Exit code 1 (vs 2 for usage errors) is the DAG's loud-failure signal.
- **Tombstone, never drop**: deletions set `ingest_docs.status='deleted'`; the row is kept so delta classifies a re-listing as `reappeared`. Deleting rows breaks that contract.
- **Idempotence via the active-only filter** (`select_applicable_deletions`): only deletions whose ledger doc is still `active` are applied — no applied_ts bookkeeping; don't add any.
- **Staged-node cleanup only for done batches** — with no batch-status column, "done" is derived as a batch with no `pending`/`staged` docs. An unfinished batch's nodes are still stage 5's input; report them (`unfinished_batches`), never delete them.
- `--run-id` scopes by batch **run_id** and deletion run_id; whole-table mode covers all batches and every still-active deletion.
- Later per block 11: Langfuse metrics + eval-DAG trigger land with block 12 — don't scaffold early.
