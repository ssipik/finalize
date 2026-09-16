from __future__ import annotations

import os
from dataclasses import dataclass

from rag_config import load_settings

DEFAULT_PG_DSN = "postgresql+psycopg://rag:rag@localhost:5433/rag_ingestion"
DEFAULT_USER_AGENT = "rag-pipeline-ingest/0.1"
# Qdrant address, collection and the quality-gate threshold come from
# rag-config's settings.yaml; an env var still overrides one for a single run.


@dataclass(frozen=True)
class Settings:
    pg_dsn: str
    http_timeout: float
    user_agent: str
    qdrant_url: str
    qdrant_collection: str
    max_parse_error_rate: float


def get_settings() -> Settings:
    shared = load_settings()
    return Settings(
        pg_dsn=os.environ.get("RAG_PG_DSN", DEFAULT_PG_DSN),
        http_timeout=float(os.environ.get("RAG_HTTP_TIMEOUT", shared.http_timeout)),
        user_agent=os.environ.get("RAG_HTTP_USER_AGENT", DEFAULT_USER_AGENT),
        qdrant_url=os.environ.get("RAG_QDRANT_URL", shared.qdrant_url),
        qdrant_collection=os.environ.get(
            "RAG_QDRANT_COLLECTION", shared.qdrant_collection
        ),
        max_parse_error_rate=float(
            os.environ.get("RAG_MAX_PARSE_ERROR_RATE", shared.max_parse_error_rate)
        ),
    )
