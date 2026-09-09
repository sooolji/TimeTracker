#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

uv sync

if [[ ! -d web/node_modules ]]; then
  (cd web && bun install)
fi

uv run uvicorn server.main:app --reload --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT

cd web
bun run dev
