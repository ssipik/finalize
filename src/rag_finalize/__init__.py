"""The finalize stage of the RAG ingestion pipeline (ARCHITECTURE.md → Ingestion orchestration).

Standalone stage module: infrastructure (settings, sources, db) is
deliberately duplicated from the other stage packages — stages are
independent blocks; dedup refactor deferred until it hurts.
"""
