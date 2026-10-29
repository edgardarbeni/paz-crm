# PAZOS

Plataforma ERP/CRM del partido PAZ: geografía electoral, candidaturas, identidad y, en fases
posteriores, padrón, defensa del voto, jurídico, atención social, encuestas y resultados.

| Documento | Contenido |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Convenciones, comandos, proceso de trabajo e índice de módulos |
| [`docs/adr/`](docs/adr/README.md) | Decisiones de arquitectura, una por archivo (tienen precedencia sobre los demás) |
| [`docs/architecture.md`](docs/architecture.md) | Stack, requisitos no funcionales, cómo está construido el núcleo y receta para agregar un módulo |
| [`docs/modules/`](docs/modules/) | Ficha de cada módulo (`_TEMPLATE.md` para los nuevos) |
| [`docs/reference/`](docs/reference/) | Modelo de datos aprobado (ER en Mermaid) y referencia geoespacial del INE |
| [`docs/history/`](docs/history/) | Brief original, plan por fases y cierres de fase (entregables, suposiciones, deuda y riesgos) |
| [`docs/api/`](docs/api/) | Colección de ejemplos de la API (Bruno) |

**Estado:** MVP completo: fases A a E aprobadas (D-77).

## Estructura

```
backend/    API FastAPI (uv) — app/core, app/modules/<módulo>, migrations (Alembic), tests
frontend/   Panel React 19 + TanStack (pnpm) — cliente de API generado en src/client
infra/      Imagen PostgreSQL 18 + PostGIS (infra/db) y Caddy (infra/caddy)
scripts/    bootstrap-env.sh, gen-api.sh
docs/       ADR, arquitectura, fichas de módulo, referencia, historia, colección Bruno
compose.yaml  Stack de desarrollo
```

## Requisitos

- Docker Desktop (o Docker Engine + Compose v2.24+)
- Para trabajar fuera de contenedores: [uv](https://docs.astral.sh/uv/) ≥ 0.13 (instala Python 3.12),
  Node 24 y pnpm 12

## Arranque rápido

```bash
./scripts/bootstrap-env.sh        # crea .env con contraseñas y llaves aleatorias
docker compose up --build         # db, redis, s3, migrate, api, scheduler, frontend, caddy, mailpit
```

| URL | Servicio |
|---|---|
| https://localhost | Panel (Caddy con TLS local; acepta el certificado o ejecuta `docker compose exec caddy caddy trust`) |
| https://localhost/docs · /redoc | Swagger UI y ReDoc |
| https://localhost/ready | Readiness (base de datos, Redis y almacenamiento) |
| http://localhost:8025 | Mailpit (correos de desarrollo) |
| http://localhost:8333 | S3 de desarrollo (SeaweedFS; objetos privados, se leen con URLs firmadas) |

Si ya tienes servicios locales en los puertos 5432, 6379, etc., cámbialos en `.env`
(variables `PAZ_*_HOST_PORT`, ver `.env.example`).

**Cambiar de rama con el stack arriba.** El panel monta la carpeta `frontend/` completa, así
que el código nuevo se ve al instante. Las dependencias viven en un volumen y se sincronizan
al arrancar: si la otra rama cambia `package.json`, ejecuta `docker compose restart frontend`.
La API recarga `app/` y `migrations/` sola; si cambian sus dependencias o hay migraciones
nuevas, ejecuta `docker compose up -d --build api migrate scheduler`.

**Primer acceso.** Crea el superadministrador y entra con él (te pedirá configurar TOTP):

```bash
docker compose exec api paz users create-superadmin
```

Después invita usuarios desde la API (`POST /api/v1/users`); los correos llegan a Mailpit.

**Geografía.** Carga Aguascalientes (descarga del INE e importación):

```bash
./scripts/seed-dev-geo.sh          # o: ./scripts/seed-dev-geo.sh 6  (Colima)
```

Para el país completo, desde una carpeta local con las 32 carpetas de la BGD:

```bash
./scripts/import-national.sh /ruta/a/paz-maps
```

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
  filas se registran con `record_audit(...)`. Las lecturas sensibles van a `audit.access_log`,
  fuera de la cadena (`record_access(...)`, D-89). Quien tiene alcance limitado solo consulta
  las entradas suyas y de los usuarios que gestiona (D-93). Para operarla:
  - `paz audit verify-chain`: recalcula la cadena y reporta el primer eslabón roto.
  - `paz audit ensure-partitions`: crea las particiones mensuales de las dos tablas. La
    programa el `scheduler`.
- **Tareas programadas (D-84, D-94).** El contenedor `scheduler` ejecuta con supercronic los
  comandos de `backend/crontab` (horas en UTC). Cada tarea toma un candado consultivo
  (`app.core.jobs.exclusive_job`), así que una ejecución manual o empalmada no se duplica.
  Fuera de compose, el mismo archivo sirve para un cron job del proveedor.
- **Almacenamiento (D-38, D-94).** `app.core.storage` (S3 genérico con el SDK de MinIO):
  objetos privados y URLs firmadas. En compose, SeaweedFS en `s3:8333`; `paz storage
  ensure-bucket` crea el bucket al migrar. Sin `PAZ_STORAGE_ENDPOINT` las funciones con
  archivos responden 503.
- **Módulos (D-94).** Cada paquete de `app/modules/` con `module.py` se registra solo:
  routers, esquema, modelos y permisos (receta en `docs/architecture.md` §7).
- **Cifrado de campos (D-31, D-32).** `FieldCipher` (AES-256-GCM con cifrado de sobre y llaves
  versionadas) y `BlindIndexer` (HMAC-SHA256). Para generar una llave: `paz keys generate`.
- **Identidad (fase B).**
  - El access token (JWT, 15 min) va en `Authorization: Bearer`. El refresh token es rotativo y va en la cookie `paz_refresh` (httpOnly, Secure, SameSite=Strict); reusarlo cierra la sesión.
  - TOTP es obligatorio para los roles con `requires_mfa`.
  - Para proteger una ruta: `user: Annotated[CurrentUser, permission(Perm.X)]`. Los permisos nuevos se declaran en el registro y se siembran por migración (D-52).
- **Geografía (fase C).**
  - Importador: `paz geo download --state N` baja la BGD y los catálogos del INE con su manifiesto. `paz geo import <carpeta|7z> --state N [--catalogs DIR] [--dry-run]` hace el upsert por llave natural sin cambiar IDs; lo que desaparece del origen queda inactivo. Cada corrida guarda su reporte en `geography.import_runs` y `import_issues`.
  - Para activar un marco nuevo: `paz geo activate --framework NOMBRE`, que remapea los alcances de los usuarios.
  - `paz geo generalize [--framework NOMBRE]` calcula las geometrías simplificadas de las teselas de zoom bajo (D-80) sin reimportar. La importación ya las calcula; el comando sirve para datos cargados antes de la migración `0010`.
  - API en `/api/v1/geography`: niveles, búsqueda por clave o nombre, `locate`, `tiles/{capa}/{z}/{x}/{y}.mvt` e importaciones. Todo queda limitado por el alcance del usuario (`PUT /api/v1/users/{id}/scopes`, D-34).
- **Personas (fase D).**
  - API en `/api/v1/people`: búsqueda por nombre sin acentos, CURP o teléfono; alta con CURP validada (estructura, dígito verificador y coherencia, D-30); contactos y domicilio cifrados; consentimientos; baja ARCO.
  - CURP, contactos y calle salen enmascarados sin `people.person.read_sensitive` (D-66).
  - `paz people purge` anonimiza a las personas cuya retención venció (D-69); la programa el `scheduler`.
- **Candidaturas (fase D).**
  - Catálogos: `/api/v1/parties`, `/office-types` (cargos nuevos sin migración) y `/validation-rules`.
  - Procesos: `/api/v1/processes` con `offices`, `municipalities`, `rules` y `coalitions`. Al crearse, todo queda deshabilitado y solo la regla "persona no duplicada" está activa (D-23, D-28).
  - Postulaciones y fórmulas: `/api/v1/nominations` y `/api/v1/formulas`, con validación, envío, aprobación, cancelación, cambios de estatus, sustitución e historial (D-67, D-68).
  - Las reglas bloqueantes devuelven 409 `rule-violation` con `violations`; se aceptan con `override` y el permiso `candidacies.rule.override`.
- **Movimiento de Paz (fase 1 de su plan).**
  - API en `/api/v1/peace-movement`: inscripción de pacificadores (persona nueva o existente,
    consentimiento del aviso vigente), pirámide de reclutamiento con `ltree`, validación,
    cambio de nivel, reasignación con toda la red, salida del movimiento, metas por estado con
    historial, configuración, coordinadores de zona y alcance por rama (D-82 a D-95).
  - Casas de Paz en `/api/v1/peace-movement/houses`: apertura con crédito automático
    (Embajador o coordinador de zona), integrantes, consolidación, reuniones con invitados,
    fotos en S3 y consentimiento para publicar la ubicación (D-85, D-96).
  - Antes de inscribir hace falta el aviso del MP: `POST /api/v1/people/privacy-notices` o, en
    desarrollo, `paz people sample-notice`.
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
```

**E2E (Playwright contra el stack real, D-73).** Desde la raíz:

```bash
./scripts/e2e.sh                 # levanta PostGIS + Redis + API sembrada y corre Playwright
./scripts/e2e.sh -g "sustitución" # argumentos extra van a Playwright
```

El script usa una base desechable con la geografía sintética de los tests
(`backend/tests/e2e/seed.py`) y un usuario por escenario, porque TOTP no acepta reusar un código.

### El panel

- **Sesión (D-74):** el access token vive solo en memoria y el refresh token en la cookie
  httpOnly. Al recargar, la sesión se restaura con la cookie. Ante un 401 el cliente renueva una
  sola vez y repite la petición. Quien aún debe enrolar TOTP va a `/enroll-mfa`.
- **Navegación por permisos:** el menú solo muestra lo que el rol permite; el backend vuelve a
  verificar todo.
- **Teclado primero:** `Ctrl+K` para ir a cualquier pantalla, `/` para buscar, `N` para crear
  en las listas, `↑ ↓ Enter` en las tablas, `Ctrl+Enter` para guardar. En el editor de
  postulaciones el cursor pasa sola a la siguiente posición tras guardar.
- **Formularios (D-75):** TanStack Form con los esquemas Zod generados y mensajes en español; la
  CURP se valida en línea con la misma regla que el backend.
- **Identidad visual (D-78):** morado PAZ `#682575` y blanco con Montserrat autoalojada; los
  tokens de color están en `frontend/src/index.css` y el logotipo en `components/brand/logo.tsx`.
- **Mapa (D-72):** MapLibre con las teselas MVT de la API sobre OpenFreeMap. Para cambiar de
  proveedor se usan `VITE_MAP_STYLE_URL` y `PAZ_MAP_TILES_ORIGIN` (CSP de producción).

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
| frontend | Biome, `tsc`, Vitest y build |
| e2e | `scripts/e2e.sh`: Playwright contra PostGIS, Redis y la API sembrada |
| api-contract | Regenera el contrato y el cliente, y falla si hay diferencias |
| images | Build de las imágenes de producción de API, panel y PostGIS (sin push) |

## Imágenes de producción

| Imagen | Contenido |
|---|---|
| `backend/Dockerfile` (`runtime`) | API como usuario sin privilegios (uid 10001), con healthcheck |
| `frontend/Dockerfile` (`runtime`) | Caddy con el panel estático y proxy a la API; requiere `PAZ_DOMAIN` y `PAZ_API_UPSTREAM` |
| `infra/db/Dockerfile` | PostgreSQL 18 + PostGIS 3, multi-arquitectura (D-43) |
