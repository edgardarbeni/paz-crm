#!/usr/bin/env bash
# Creates .env for local development with random passwords and encryption keys.
# Never reuse these values outside your machine.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env && "${1:-}" != "--force" ]]; then
  echo ".env ya existe (usa --force para regenerarlo; perderás acceso a datos cifrados)." >&2
  exit 1
fi

rand_b64() { openssl rand -base64 32; }
rand_pw() { openssl rand -hex 16; }

sed \
  -e "s|^PAZ_DB_OWNER_PASSWORD=.*|PAZ_DB_OWNER_PASSWORD=$(rand_pw)|" \
  -e "s|^PAZ_DB_APP_PASSWORD=.*|PAZ_DB_APP_PASSWORD=$(rand_pw)|" \
  -e "s|^PAZ_ENCRYPTION_KEYS=.*|PAZ_ENCRYPTION_KEYS=1:$(rand_b64)|" \
  -e "s|^PAZ_BLIND_INDEX_KEY=.*|PAZ_BLIND_INDEX_KEY=$(rand_b64)|" \
  -e "s|^PAZ_JWT_SECRET=.*|PAZ_JWT_SECRET=$(openssl rand -hex 32)|" \
  .env.example > .env

echo ".env creado. Siguiente paso: docker compose up --build"
