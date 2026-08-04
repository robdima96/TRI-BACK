#!/bin/sh
# Start study UI on Cloud Run: init SQLite, Redis, Reflex backend, then Caddy on $PORT.
set -eu

PORT="${PORT:-8080}"
export PORT
export DIGIMSK_STUDY_DB="${DIGIMSK_STUDY_DB:-/mnt/digimsk/study/digimsk.db}"
# Keep Granian light on Cloud Run CPU
export REFLEX_GRANIAN_WORKERS="${REFLEX_GRANIAN_WORKERS:-1}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

mkdir -p "$(dirname "$DIGIMSK_STUDY_DB")"
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

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
