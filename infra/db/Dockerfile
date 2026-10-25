# PostgreSQL 18 + PostGIS 3 (multi-arch: amd64 and arm64).
# The official postgis/postgis:18-3.6 image is amd64-only (D-43), so we install PostGIS from
# the PGDG apt repository that the official postgres image already configures.
FROM postgres:18-bookworm

ARG POSTGIS_MAJOR=3
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      "postgresql-${PG_MAJOR}-postgis-${POSTGIS_MAJOR}" \
      "postgresql-${PG_MAJOR}-postgis-${POSTGIS_MAJOR}-scripts" \
 && rm -rf /var/lib/apt/lists/*

COPY initdb/ /docker-entrypoint-initdb.d/
