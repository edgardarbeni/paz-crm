# Cierre de fase A — Infraestructura base, core y CI

**Fecha:** 2026-10-24 · **Rama:** `feat/phase-a-foundation` · **Estado:** aprobada el 2026-10-24 · PR [#1](https://github.com/edgardarbeni/paz-crm/pull/1).

## Criterios de aceptación (PLAN_FASES.md)

| Criterio | Resultado | Evidencia |
|---|---|---|
| `docker compose up` levanta todo y `/ready` responde 200 | ✅ | `https://localhost/ready` → `{"status":"ok","database":"ok","redis":"ok"}` a través de Caddy; migraciones en `0002`; `paz audit verify-chain` OK dentro del contenedor |
| CI verde | ✅ | [Ejecución 40145453886](https://github.com/edgardarbeni/paz-crm/actions/runs/40145453886) en el PR #1: changes, backend, frontend, api-contract e images en verde |
| Tests de core: Problem Details | ✅ | `tests/unit/test_app_errors_and_headers.py` |
| Tests de core: cifrado y rotación de llave | ✅ | `tests/unit/test_crypto.py` (incluye manipulación, contexto equivocado y llave retirada) |
| Tests de core: cadena de auditoría y detección de alteraciones | ✅ | `tests/integration/test_audit_log.py` (fila editada, filas borradas en medio y al final, 10 escritores concurrentes, permisos del rol app, inmutabilidad para el dueño) |
| Tests de core: paginación por cursor | ✅ | `tests/unit/test_pagination.py`, `tests/integration/test_pagination_db.py` (direcciones mixtas, recorre todas las filas sin duplicados) |
| Verificación de PG18 + PostGIS administrado (D-05) | ✅ | DigitalOcean (Standard Edition) y AWS RDS ofrecen PG18 + PostGIS; ver R-1 |

**Números:**
- **Backend:** 58 tests (39 unitarios + 19 de integración sobre PostgreSQL 18.x + PostGIS 3 y Redis 8 reales); cobertura **96 %** (mínimo 85 %); `ruff` y `mypy --strict` sin observaciones.
- **Frontend:** 8 tests de Vitest y 2 de Playwright; Biome y `tsc` sin observaciones; el build de producción pasa.
- **Imágenes de producción:** compilan. La API corre como uid 10001 (409 MB); el panel se sirve desde Caddy (93 MB).

## Entregables

| Área | Entregado |
|---|---|
| Monorepo | `backend/`, `frontend/`, `infra/`, `scripts/` y `docs/` |
| Desarrollo | `compose.yaml` (db, redis, migrate, api, frontend, caddy, mailpit), `scripts/bootstrap-env.sh` |
| Core del backend | Configuración (`PAZ_*`), logs JSON con `request_id`/`trace_id`, OpenTelemetry (OTLP opcional), Problem Details, CORS y cabeceras de seguridad, sesión async, mixins de modelos (UUIDv7, timestamps, soft-delete, importados), Redis, cifrado (sobre + rotación + blind index), bitácora inmutable, paginación por cursor, `/health` y `/ready`, CLI `paz` |
| Migraciones | `0001`: extensiones, esquemas, GRANT y `f_unaccent`. `0002`: bitácora particionada con cadena de hashes |
| Frontend | Vite + React 19 + TanStack Router/Query, Tailwind 4 + shadcn/ui, cliente Hey API (SDK + hooks + Zod), pantalla de estado del sistema, link "saltar al contenido" |
| Contrato | `scripts/gen-api.sh`; el job `api-contract` falla si el cliente queda desactualizado |
| CI | `.github/workflows/ci.yml` con filtros por ruta |
| Documentación | `README.md`, `.env.example`, colección Bruno (`docs/api/`), decisiones D-43 a D-47 |

## Suposiciones

1. `/health` y `/ready` quedan fuera de `/api/v1` (convención de orquestadores; D-46).
2. Los títulos de Problem Details van en español; `code` es estable y en inglés (kebab-case).
3. El `X-Request-ID` entrante se acepta si tiene 8–64 caracteres `[A-Za-z0-9._-]`.
4. El dueño de la base de datos en desarrollo es superusuario (lo requieren `CREATE EXTENSION postgis` y las funciones `SECURITY DEFINER`). En un servicio administrado se usa el rol administrador del proveedor.
5. Se crean particiones de la bitácora 3 meses hacia adelante; la partición `DEFAULT` absorbe cualquier atraso.

## Deuda técnica

| # | Deuda | Cuándo atenderla |
|---|---|---|
| DT-1 | TypeScript fijado en 6 por Hey API (D-47) | Cuando Hey API soporte TS 7 |
| DT-2 | Solo existe `EnvKeyProvider`; falta el proveedor KMS (AWS KMS) | Antes del primer despliegue con datos reales |
| DT-3 | Rotar la llave del blind index obliga a recalcular índices; aún no hay comando para hacerlo | Fase D (personas) |
| DT-4 | `paz audit ensure-partitions` debe programarse con cron en producción | Al definir el despliegue |
| DT-5 | `uvicorn --forwarded-allow-ips *` confía en cualquier proxy; depende de que la API no sea accesible fuera de la red interna | Al definir el despliegue: restringir a la IP o red del proxy |
| DT-6 | Imagen de la API de 409 MB (OpenTelemetry, cryptography, GeoAlchemy2) | Optimizar si afecta los tiempos de despliegue |
| DT-7 | Sin umbral de cobertura en el frontend | Fase E, cuando haya lógica de UI significativa |
| DT-8 | Compose no incluye collector de OpenTelemetry (exportar es opcional) | Al definir la observabilidad de staging |

## Riesgos

| # | Riesgo | Mitigación / decisión |
|---|---|---|
| ~~R-1~~ | ~~Disponibilidad de PostGIS para PG18 en servicios administrados~~ | **Resuelto.** La [lista oficial de extensiones de DigitalOcean](https://docs.digitalocean.com/products/databases/postgresql/details/supported-extensions/) incluye `postgis` en PostgreSQL 18 (Standard Edition) y [AWS RDS](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-rds-postgresql/) ofrece PG 18.4 + PostGIS 3.6.3. Al crear el clúster en DO hay que elegir **Standard Edition** y comprobar `CREATE EXTENSION postgis` |
| R-2 | El bloqueo de `audit.chain_head` serializa todas las escrituras auditadas | Medir en las pruebas de carga de C/D. Alternativas: cadenas por partición o encolar las entradas |
| R-3 | Paquetes en versiones muy recientes (SQLAlchemy 2.1, FastAPI 0.162, Vite 8, Vitest 5, React Table 9) con APIs que pueden diferir de la documentación conocida | El lockfile fija las versiones; los tests y `filterwarnings=error` detectan deprecaciones |
| ~~R-4~~ | ~~El CI no se ha ejecutado aún en GitHub~~ | **Resuelto:** primera ejecución en verde en el PR #1 |
