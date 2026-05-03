#!/usr/bin/env bash
set -euo pipefail

# Run from repo root:  cd .../bot && bash scripts/sockeye/setup_venv.sh
BOT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${BOT_ROOT}"

if [[ "${PYTHON:+x}" ]]; then
  PY="${PYTHON}"
else
  PY="python3"
fi

"${PY}" -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate

python -m pip install -U pip
python -m pip install -e ".[dev]"

echo ""
echo "OK: venv at ${BOT_ROOT}/.venv"
echo "    source ${BOT_ROOT}/.venv/bin/activate"
