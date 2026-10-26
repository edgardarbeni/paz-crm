# D-43 · Imagen propia de PostgreSQL 18 + PostGIS

- **Estado:** Aceptada
- **Área:** Fase A — implementación

`infra/db/Dockerfile` parte de `postgres:18-bookworm` (multi-arquitectura) e instala PostGIS 3 desde PGDG.
*Motivo:* la imagen oficial `postgis/postgis:18-3.6` solo existe para amd64; en Macs arm64 correría emulada. La misma imagen sirve para desarrollo, CI (testcontainers) y como referencia de producción.
