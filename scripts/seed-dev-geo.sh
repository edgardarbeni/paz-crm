#!/usr/bin/env bash
# Development seed (D-20): downloads a state's BGD + INE catalogs and imports it into the
# docker compose database. Default: Aguascalientes (01). Data lands in ./data (not versioned).
#   ./scripts/seed-dev-geo.sh            # Aguascalientes
#   ./scripts/seed-dev-geo.sh 6          # Colima
set -euo pipefail
cd "$(dirname "$0")/.."
STATE="${1:-1}"
NN=$(printf %02d "$STATE")
set -a; . ./.env; set +a
export PAZ_DATABASE_URL="postgresql://${PAZ_DB_APP_USER:-paz_app}:${PAZ_DB_APP_PASSWORD}@localhost:${PAZ_DB_HOST_PORT:-5432}/${PAZ_DB_NAME:-paz}"
export PAZ_MIGRATIONS_DATABASE_URL="postgresql://${PAZ_DB_OWNER_USER:-paz_owner}:${PAZ_DB_OWNER_PASSWORD}@localhost:${PAZ_DB_HOST_PORT:-5432}/${PAZ_DB_NAME:-paz}"
export PAZ_REDIS_URL="redis://localhost:${PAZ_REDIS_HOST_PORT:-6379}/0"
cd backend
uv run paz geo download --state "$STATE" --dest ../data/ine
ARCHIVE=$(ls ../data/ine/"$NN"/bgd/*.7z | head -1)
uv run paz geo import "$ARCHIVE" --state "$STATE" --catalogs "../data/ine/$NN"
