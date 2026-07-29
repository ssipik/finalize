from rag_finalize.finalize import parse_error_rate, select_applicable_deletions


class TestParseErrorRate:
    def test_no_docs_is_zero(self):
        assert parse_error_rate([]) == 0.0

    def test_all_good_is_zero(self):
        assert parse_error_rate(["embedded", "skipped_unchanged"]) == 0.0

    def test_counts_only_error_status(self):
        assert parse_error_rate(["embedded", "error", "error", "staged"]) == 0.5


def deletion(manifest_id=1, run_id="r9"):
    """A deletion row: the ledger's live sighting plus the detecting run."""
    return {"manifest_id": manifest_id, "run_id": run_id}


class TestSelectApplicableDeletions:
    def test_active_ledger_doc_is_applied(self):
        ledger = {1: {"status": "active"}}
        assert len(select_applicable_deletions([deletion()], ledger)) == 1

    def test_already_tombstoned_is_skipped(self):
        # re-running finalize must be idempotent without deletion-state bookkeeping
        ledger = {1: {"status": "deleted"}}
        assert select_applicable_deletions([deletion()], ledger) == []

    def test_never_ingested_is_skipped(self):
        assert select_applicable_deletions([deletion()], {}) == []

    def test_stale_deletion_after_reappearance_is_skipped(self):
        # doc deleted under sighting 1, later reappeared and was re-ingested,
        # so the ledger moved to sighting 5. The old deletion row must not
        # take the freshly ingested document down with it.
        ledger = {5: {"status": "active"}}
        assert select_applicable_deletions([deletion(manifest_id=1)], ledger) == []
