"""Dev/ops entrypoint: ``python -m rag_finalize``.

Thin argparse wrapper over :func:`rag_finalize.finalize.run_finalize` — the
library function remains the API that Airflow tasks import directly; keep
all stage logic out of this module.
"""

from __future__ import annotations

import argparse
import logging
import sys

from rag_finalize.finalize import QualityGateError, run_finalize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rag_finalize",
        description="FINALIZE stage: quality gate, apply deletions "
        "(Qdrant + ledger tombstones), clear staged nodes.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run whose batches/deletions to finalize (the rag_plan run_id = "
        "ingest_batches.run_id). Omitted: whole-table — all batches, every "
        "still-active deletion",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        report = run_finalize(run_id=args.run_id)
    except QualityGateError as exc:
        print(f"QUALITY GATE FAILED: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"finalize {report.run_id}: docs={report.doc_counts} "
        f"error_rate={report.error_rate:.1%} "
        f"deletions_applied={report.deletions_applied} "
        f"staged_rows_deleted={report.staged_rows_deleted}"
        + (
            f" — WARNING: {report.unfinished_batches} unfinished batch(es) kept their staged nodes"
            if report.unfinished_batches
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
