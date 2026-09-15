#!/bin/sh
# Start study UI on Cloud Run: init SQLite, Redis, Reflex backend, then Caddy on $PORT.
set -eu

CLOUD_RUN_PORT="${PORT:-8080}"
# Reflex maps $PORT to --frontend-port. Cloud Run injects 8080, which breaks
# `--backend-only` ("Cannot specify --frontend-port when not running frontend").
unset PORT

# Prefer TRI_BACK_*; fall back to DIGIMSK_* and the existing GCS study DB filename.
if [ -z "${TRI_BACK_STUDY_DB:-}" ]; then
  if [ -n "${DIGIMSK_STUDY_DB:-}" ]; then
    export TRI_BACK_STUDY_DB="$DIGIMSK_STUDY_DB"
  else
    export TRI_BACK_STUDY_DB="/mnt/tri-back/study/tri_back.db"
  fi
fi
if [ ! -f "$TRI_BACK_STUDY_DB" ] && [ -f /mnt/tri-back/study/digimsk.db ]; then
  export TRI_BACK_STUDY_DB=/mnt/tri-back/study/digimsk.db
fi
export DIGIMSK_STUDY_DB="${DIGIMSK_STUDY_DB:-$TRI_BACK_STUDY_DB}"
# Keep Granian light on Cloud Run CPU
export REFLEX_GRANIAN_WORKERS="${REFLEX_GRANIAN_WORKERS:-1}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

mkdir -p "$(dirname "$TRI_BACK_STUDY_DB")"
python scripts/init_db.py

if [ -f /study/Caddyfile ]; then
  mkdir -p /etc/caddy
  cp /study/Caddyfile /etc/caddy/Caddyfile
fi

redis-server --daemonize yes --save "" --appendonly no || {
  echo "redis-server failed to start" >&2
  exit 1
}

# Backend first (background); Caddy becomes PID 1 on $PORT once ready.
reflex run --env prod --backend-only --backend-host 127.0.0.1 --backend-port 8000 &
REFLEX_PID=$!

echo "Waiting for Reflex backend on 127.0.0.1:8000 ..."
i=0
while [ "$i" -lt 90 ]; do
  if curl -sf "http://127.0.0.1:8000/ping" >/dev/null 2>&1; then
    echo "Reflex backend is up."
    break
  fi
  if ! kill -0 "$REFLEX_PID" 2>/dev/null; then
    echo "Reflex process exited before becoming ready" >&2
    wait "$REFLEX_PID" || true
    exit 1
  fi
  i=$((i + 1))
  sleep 1
done

if ! curl -sf "http://127.0.0.1:8000/ping" >/dev/null 2>&1; then
  echo "Timed out waiting for Reflex /ping" >&2
  exit 1
fi

export PORT="$CLOUD_RUN_PORT"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
