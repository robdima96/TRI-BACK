#!/usr/bin/env bash
set -euo pipefail

BOT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${BOT_ROOT}"

if [[ ! -f .venv/bin/activate ]]; then
  echo "Missing .venv. Run from ${BOT_ROOT}: bash scripts/sockeye/setup_venv.sh"
  exit 1
fi
# shellcheck source=/dev/null
source .venv/bin/activate

export PORT="${PORT:-8000}"
echo "DigiMSKbot: uvicorn host=0.0.0.0 port=${PORT} cwd=${BOT_ROOT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
