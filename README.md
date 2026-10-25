# PAZOS

Plataforma ERP/CRM del partido PAZ: geografía electoral, candidaturas, identidad y, en fases
posteriores, padrón, defensa del voto, jurídico, atención social, encuestas y resultados.

| Documento | Contenido |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Brief del proyecto: alcance, requisitos, stack y proceso |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | Registro de decisiones (tiene precedencia sobre los demás) |
| [`docs/MODELO_DATOS.md`](docs/MODELO_DATOS.md) | Modelo de datos aprobado (ER en Mermaid) |
| [`docs/PLAN_FASES.md`](docs/PLAN_FASES.md) | Plan por fases aprobado |
| [`docs/fases/`](docs/fases/) | Cierre de cada fase: entregables, suposiciones, deuda y riesgos |
| [`docs/api/`](docs/api/) | Colección de ejemplos de la API (Bruno) |

**Estado:** fase A aprobada · fase B (identidad) implementada, pendiente de aprobación.

## Estructura

```
backend/    API FastAPI (uv) — app/core, app/modules/<módulo>, migrations (Alembic), tests
frontend/   Panel React 19 + TanStack (pnpm) — cliente de API generado en src/client
infra/      Imagen PostgreSQL 18 + PostGIS (infra/db) y Caddy (infra/caddy)
scripts/    bootstrap-env.sh, gen-api.sh
docs/       Decisiones, modelo, plan, cierres de fase, colección Bruno
compose.yaml  Stack de desarrollo
```

## Requisitos

- Docker Desktop (o Docker Engine + Compose v2.24+)
- Para trabajar fuera de contenedores: [uv](https://docs.astral.sh/uv/) ≥ 0.13 (instala Python 3.12),
  Node 24 y pnpm 12

## Arranque rápido

```bash
./scripts/bootstrap-env.sh        # crea .env con contraseñas y llaves aleatorias
docker compose up --build         # db, redis, migrate, api, frontend, caddy, mailpit
```

| URL | Servicio |
|---|---|
| https://localhost | Panel (Caddy con TLS local; acepta el certificado o ejecuta `docker compose exec caddy caddy trust`) |
| https://localhost/docs · /redoc | Swagger UI y ReDoc |
| https://localhost/ready | Readiness (base de datos + Redis) |
| http://localhost:8025 | Mailpit (correos de desarrollo) |

Si ya tienes servicios locales en los puertos 5432, 6379, etc., cámbialos en `.env`
(variables `PAZ_*_HOST_PORT`, ver `.env.example`).

**Primer acceso.** Crea el superadministrador y entra con él (te pedirá configurar TOTP):

```bash
docker compose exec api paz users create-superadmin
```

Después invita usuarios desde la API (`POST /api/v1/users`); los correos llegan a Mailpit.

## Backend

```bash
cd backend
uv sync                              # dependencias (incluye grupo dev)
uv run ruff check . && uv run ruff format --check .
uv run mypy                          # modo estricto
uv run pytest --cov                  # levanta PostgreSQL 18 + PostGIS y Redis con testcontainers
uv run pytest -m "not integration"   # solo tests unitarios, sin Docker
uv run alembic upgrade head          # migraciones (usa PAZ_MIGRATIONS_DATABASE_URL)
uv run paz --help                    # CLI de operación
```

- **Roles de base de datos.** Las migraciones corren con el rol dueño
  (`PAZ_MIGRATIONS_DATABASE_URL`); la API se conecta con `paz_app`, que solo recibe los GRANT
  que emiten las migraciones. `infra/db/initdb` crea `paz_app` en desarrollo y CI.
- **Bitácora inmutable (D-37).** `audit.audit_log` es append-only y tiene cadena de hashes. Toda
  escritura del ORM queda registrada automáticamente (`AuditedSession`); los eventos que no son
  filas se registran con `record_audit(...)`. Para operarla:
  - `paz audit verify-chain`: recalcula la cadena y reporta el primer eslabón roto.
  - `paz audit ensure-partitions`: crea las particiones mensuales. Se programa con cron
    usando el rol dueño.
- **Cifrado de campos (D-31, D-32).** `FieldCipher` (AES-256-GCM con cifrado de sobre y llaves
  versionadas) y `BlindIndexer` (HMAC-SHA256). Para generar una llave: `paz keys generate`.
- **Identidad (fase B).**
  - El access token (JWT, 15 min) va en `Authorization: Bearer`. El refresh token es rotativo y va en la cookie `paz_refresh` (httpOnly, Secure, SameSite=Strict); reusarlo cierra la sesión.
  - TOTP es obligatorio para los roles con `requires_mfa`.
  - Para proteger una ruta: `user: Annotated[CurrentUser, permission(Perm.X)]`. Los permisos nuevos se declaran en el registro y se siembran por migración (D-52).
- **Errores.** Siempre RFC 9457 (`application/problem+json`): `type` es `urn:pazos:problem:<code>`
  e incluye `request_id`.
- **Paginación.** Por cursor (`app.core.pagination`): `limit` ≤ 200, `cursor` opaco y `sort`
  con campos de una lista permitida.

## Frontend

```bash
cd frontend
pnpm install
pnpm dev            # http://localhost:5173 (proxy de /api a localhost:8000)
pnpm lint           # Biome
pnpm typecheck
pnpm test           # Vitest + Testing Library
pnpm e2e            # Playwright contra el build de producción
```

### Contrato de API y cliente generado

El cliente (`frontend/src/client`) se genera con Hey API a partir del OpenAPI del backend.
Escribir llamadas `fetch` a mano está prohibido. Después de cualquier cambio en rutas o
esquemas, regenera ambos y haz commit:

```bash
./scripts/gen-api.sh
```

El CI falla si `frontend/openapi.json` o el cliente generado están desactualizados.

## CI (GitHub Actions)

`.github/workflows/ci.yml` corre según las carpetas que cambiaron:

| Job | Qué corre |
|---|---|
| backend | ruff, mypy y pytest con cobertura ≥ 85 % sobre PostGIS real |
| frontend | Biome, `tsc`, Vitest, build y Playwright |
| api-contract | Regenera el contrato y el cliente, y falla si hay diferencias |
| images | Build de las imágenes de producción de API, panel y PostGIS (sin push) |

## Imágenes de producción

| Imagen | Contenido |
|---|---|
| `backend/Dockerfile` (`runtime`) | API como usuario sin privilegios (uid 10001), con healthcheck |
| `frontend/Dockerfile` (`runtime`) | Caddy con el panel estático y proxy a la API; requiere `PAZ_DOMAIN` y `PAZ_API_UPSTREAM` |
| `infra/db/Dockerfile` | PostgreSQL 18 + PostGIS 3, multi-arquitectura (D-43) |
