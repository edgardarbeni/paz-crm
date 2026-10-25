#!/usr/bin/env bash
# Creates the least-privilege application role on first boot (development / CI).
# Migrations run as POSTGRES_USER (owner); the API connects as PAZ_DB_APP_USER and only
# receives the grants issued by the migrations.
set -euo pipefail

APP_USER="${PAZ_DB_APP_USER:-paz_app}"
APP_PASSWORD="${PAZ_DB_APP_PASSWORD:-paz_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$APP_USER" -v app_password="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
              :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SQL
