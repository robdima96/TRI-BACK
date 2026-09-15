# TRI-BACK bot for Cloud Run (repo-root entrypoint).
# Cloud Run "Continuous deployment from GitHub" looks for ./Dockerfile by default.
# Canonical copy also lives at:
#   bot/app/services/public_host/cloud_run/Dockerfile.bot
#
# Build locally from this monorepo root:
#   docker build -t tri-back-bot .

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRI_BACK_RAG=0 \
    TRI_BACK_GRAPH_RAG=1 \
    TRI_BACK_LOAD_RAG=0 \
    TRI_BACK_GENERATOR_BACKEND=vertex \
    TRI_BACK_GLINER_MODEL_DIR=/mnt/tri-back/models/gliner \
    TRI_BACK_GRAPH_CSV=/mnt/tri-back/graph/v4/red_flags_edges_v4_2026.9.10.csv \
    TRI_BACK_GRAPH_FACTORS=/mnt/tri-back/graph/v4/red_flags_factors_v4_2026.9.10.csv \
    TRI_BACK_GRAPH_INVENTORY=/mnt/tri-back/graph/v4/red_flags_inventory_v4_2026.9.10.json \
    TRI_BACK_SESSION_STORE_DIR=/mnt/tri-back/sessions \
    TRI_BACK_CHECKPOINT_SQLITE=/tmp/langgraph_checkpoints.sqlite

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bot/pyproject.toml bot/README.md bot/readme.txt ./
COPY bot/app ./app
RUN pip install --upgrade pip \
    && pip install -e ".[generator-api,gliner]"

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
