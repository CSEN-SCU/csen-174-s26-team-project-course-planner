#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$ROOT/.pycache_dir}"

exec python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8010}"
