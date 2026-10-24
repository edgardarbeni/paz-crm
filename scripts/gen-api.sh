#!/usr/bin/env bash
# Regenerates the API contract and the typed frontend client (Hey API).
# Run after any change to backend routes or schemas; CI fails if they are stale.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && uv run paz openapi export ../frontend/openapi.json)
(cd frontend && pnpm gen:api)
