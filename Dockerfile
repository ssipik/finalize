# Stage-6 (FINALIZE) image — the future Nomad batch-job artifact.
FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-emit-project -o /tmp/requirements.txt \
 && pip install --no-cache-dir -r /tmp/requirements.txt

COPY src ./src
RUN pip install --no-cache-dir --no-deps .

COPY config ./config
ENV RAG_SOURCES_PATH=/app/config/sources.yaml
