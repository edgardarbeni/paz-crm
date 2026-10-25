#!/usr/bin/env bash
# End-to-end tests of the panel against the real stack (D-73): PostgreSQL 18 + PostGIS, Redis,
# migrations, synthetic seed, API (uvicorn) and the production build of the panel (Playwright).
# Runs the same locally and in CI. Extra arguments go to Playwright (e.g. --ui, -g "sustitución").
set -euo pipefail
cd "$(dirname "$0")/.."

PG_IMAGE="${PAZ_TEST_PG_IMAGE:-paz/postgres-postgis:18}"
DB_PORT="${PAZ_E2E_DB_PORT:-55432}"
REDIS_PORT="${PAZ_E2E_REDIS_PORT:-56379}"
API_PORT="${PAZ_E2E_API_PORT:-8010}"
PREFIX="paz-e2e-$$"

cleanup() {
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  docker rm -f "$PREFIX-db" "$PREFIX-redis" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker image inspect "$PG_IMAGE" >/dev/null 2>&1; then
  docker build -t "$PG_IMAGE" infra/db
fi
docker run -d --name "$PREFIX-db" -p "127.0.0.1:$DB_PORT:5432" \
  -e POSTGRES_DB=paz_e2e -e POSTGRES_USER=paz_owner -e POSTGRES_PASSWORD=e2e-owner \
  -e PAZ_DB_APP_USER=paz_app -e PAZ_DB_APP_PASSWORD=e2e-app "$PG_IMAGE" >/dev/null
docker run -d --name "$PREFIX-redis" -p "127.0.0.1:$REDIS_PORT:6379" redis:8-alpine >/dev/null

# Throwaway secrets: this database lives only for the run.
export PAZ_ENVIRONMENT=test
export PAZ_API_DOCS_ENABLED=false
export PAZ_CORS_ALLOWED_ORIGINS="http://localhost:4173"
export PAZ_PUBLIC_BASE_URL="http://localhost:4173"
export PAZ_DATABASE_URL="postgresql://paz_app:e2e-app@127.0.0.1:$DB_PORT/paz_e2e"
export PAZ_MIGRATIONS_DATABASE_URL="postgresql://paz_owner:e2e-owner@127.0.0.1:$DB_PORT/paz_e2e"
export PAZ_DATABASE_APP_ROLE=paz_app
export PAZ_REDIS_URL="redis://127.0.0.1:$REDIS_PORT/0"
export PAZ_ENCRYPTION_KEYS="1:$(openssl rand -base64 32)"
export PAZ_ENCRYPTION_ACTIVE_KEY_VERSION=1
export PAZ_BLIND_INDEX_KEY="$(openssl rand -base64 32)"
export PAZ_JWT_SECRET="$(openssl rand -hex 32)"
export PAZ_MAIL_BACKEND=memory
export PAZ_LOGIN_RATE_LIMIT_PER_IP=1000

echo "Esperando a PostgreSQL…"
for _ in $(seq 1 60); do
  docker exec "$PREFIX-db" pg_isready -U paz_owner -d paz_e2e >/dev/null 2>&1 && break
  sleep 1
done
sleep 2  # initdb restarts the server once after the init scripts

(
  cd backend
  uv run alembic upgrade head
  uv run python -m tests.e2e.seed ../frontend/e2e/.seed.json
  uv run uvicorn app.asgi:app --port "$API_PORT" --log-level warning &
  echo $! > "/tmp/$PREFIX-api.pid"
)
API_PID="$(cat "/tmp/$PREFIX-api.pid")"
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$API_PORT/ready" >/dev/null && break
  sleep 1
done

cd frontend
VITE_DEV_API_PROXY="http://127.0.0.1:$API_PORT" pnpm exec playwright test "$@"
