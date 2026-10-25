#!/usr/bin/env bash
# Imports the 32 states from a local BGD folder (e.g. paz-maps/) with INE catalogs.
# Usage: scripts/import-national.sh /path/to/paz-maps [first_state] [last_state]
# Requires PAZ_* variables (see .env.example); uses the owner role (PAZ_MIGRATIONS_DATABASE_URL).
set -euo pipefail
cd "$(dirname "$0")/../backend"
SOURCE="${1:?Carpeta con las 32 carpetas NN NOMBRE}"
FIRST="${2:-1}"; LAST="${3:-32}"
for state in $(seq "$FIRST" "$LAST"); do
  start=$(date +%s)
  uv run paz geo download --state "$state" --no-bgd >/dev/null
  if uv run paz geo import "$SOURCE" --state "$state" --catalogs "../data/ine/$(printf %02d "$state")" > "../data/ine/import-$(printf %02d "$state").json"; then
    status=ok
  else
    status=FAILED
  fi
  echo "estado $(printf %02d "$state"): $status en $(( $(date +%s) - start )) s"
done
