from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PG_DSN = "postgresql+psycopg://rag:rag@localhost:5433/rag_ingestion"
DEFAULT_USER_AGENT = "rag-pipeline-ingest/0.1"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_QDRANT_COLLECTION = "rag_chunks"
# Quality gate: fail the DAG loudly when more than this share of
# a run's batch docs ended in parse error — a source-site redesign must not
# silently poison the index.
DEFAULT_MAX_PARSE_ERROR_RATE = 0.2


@dataclass(frozen=True)
class Settings:
    pg_dsn: str
    http_timeout: float
    user_agent: str
    qdrant_url: str
    qdrant_collection: str
    max_parse_error_rate: float


def get_settings() -> Settings:
    return Settings(
        pg_dsn=os.environ.get("RAG_PG_DSN", DEFAULT_PG_DSN),
        http_timeout=float(os.environ.get("RAG_HTTP_TIMEOUT", "30")),
        user_agent=os.environ.get("RAG_HTTP_USER_AGENT", DEFAULT_USER_AGENT),
        qdrant_url=os.environ.get("RAG_QDRANT_URL", DEFAULT_QDRANT_URL),
        qdrant_collection=os.environ.get(
            "RAG_QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION
        ),
        max_parse_error_rate=float(
            os.environ.get("RAG_MAX_PARSE_ERROR_RATE", DEFAULT_MAX_PARSE_ERROR_RATE)
        ),
    )
