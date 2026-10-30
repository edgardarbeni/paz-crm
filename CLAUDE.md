# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contexto

PAZOS es la plataforma ERP/CRM del partido político nacional PAZ. Concentra en un solo sistema
áreas que hoy no resuelve ningún producto del mercado: candidaturas, geografía electoral,
padrones, defensa del voto, jurídico, atención social, encuestas, publicidad exterior y
resultados electorales. Sus prioridades son:

- facilidad de uso;
- velocidad de captura y de consulta;
- capacidad de moldearse a futuro;
- infraestructura de alto rendimiento.

**Estado:** el MVP está completo (fases A–E, D-77). Desde entonces se agregaron la identidad
visual (D-78), la búsqueda geográfica por nombre (D-79) y el módulo Movimiento de Paz (D-82 a
D-100). No hay portal de pacificadores: el personal usa el panel y quien está en campo usará la
App (Flutter, todavía sin construir). Cada módulo nuevo se especifica primero en su ficha de
`docs/modules/`.

## Documentación

| Ruta | Contenido |
|---|---|
| `docs/adr/` | Decisiones, una por archivo (`D-NN-tema.md`) e índice en `README.md`. **Tienen precedencia** sobre este archivo, las fichas y `reference/` |
| `docs/architecture.md` | Cómo está construido el núcleo: stack, requisitos no funcionales, routers, permisos, alcance, auditoría, migraciones, receta de módulo nuevo y diferencias conocidas |
| `docs/modules/` | Una ficha por módulo, a partir de `_TEMPLATE.md` |
| `docs/reference/` | `data-model.md` (ER completo aprobado, D-41) y `DISENO_BD_GEOESPACIAL.md` (referencia de datos del INE) |
| `docs/history/` | `BRIEF_MVP.md` (brief original íntegro), `PLAN_FASES.md` y cierres de fase en `fases/` |
| `docs/api/` | Colección Bruno de ejemplos de la API |

## Índice de módulos

| Módulo | Paquete backend | Estado | Ficha |
|---|---|---|---|
| Identidad y acceso (usuarios, roles, 2FA, alcances, bitácora) | `app/modules/identity`, `app/modules/audit` | Implementado | [identity.md](docs/modules/identity.md) |
| Geografía electoral | `app/modules/geography` | Implementado | [geography.md](docs/modules/geography.md) |
| Personas (base del futuro padrón) | `app/modules/people` | Implementado | [people.md](docs/modules/people.md) |
| Candidaturas | `app/modules/candidacies` | Implementado | [candidacies.md](docs/modules/candidacies.md) |
| Movimiento de Paz (pacificadores, Casas de Paz, metas) | `app/modules/peace_movement` | Implementado (API y panel) | [peace-movement.md](docs/modules/peace-movement.md) |
| Estructura del partido (cargos, nombramientos, coordinaciones territoriales) | `app/modules/party_structure` | En curso: fases 0 a 3 (concesiones, catálogo, órganos, nombramientos y acceso; D-106 a D-109) | [party-structure.md](docs/modules/party-structure.md) |

Módulos futuros nombrados en el brief, todavía sin ficha:
- padrón de militancia y afiliación al partido (aparte del Movimiento de Paz);
- información electoral histórica;
- defensa del voto;
- jurídico;
- atención social y necesidades comunitarias;
- encuestas y poll of polls;
- vallas y bardas;
- resultados preliminares y cómputos distritales;
- cartografía no electoral (D-13).

## Comandos

Backend (`cd backend`):
```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy                       # estricto, cubre app/ y tests/ (el CI lo corre así)
TESTCONTAINERS_RYUK_DISABLED=true uv run pytest            # PostGIS + Redis reales; cobertura ≥ 85 %
uv run pytest -m "not integration"                          # solo unitarios, sin Docker
uv run pytest tests/integration/geography/test_geography_api.py::test_name   # un test
uv run alembic revision --autogenerate --rev-id 0010 -m "…"  # revisiones numeradas en secuencia
uv run paz --help                 # CLI: users, geo, audit, keys, people, openapi
```

Frontend (`cd frontend`):
```bash
pnpm exec biome ci . && pnpm typecheck && pnpm test && pnpm build   # lo mismo que el CI
pnpm exec vitest run src/lib/search.test.ts                         # un archivo
```

Desde la raíz:
```bash
./scripts/gen-api.sh       # regenera frontend/openapi.json y src/client; obligatorio tras cambiar rutas o esquemas
./scripts/e2e.sh [-g "…"]  # Playwright contra un stack desechable (PostGIS, Redis, API sembrada)
docker compose up --build  # stack de desarrollo en https://localhost (ver README)
```

### El stack local del usuario

El usuario corre `docker compose` desde este checkout. No cambies de rama aquí sin avisar.
Para trabajar en otra rama, usa un git worktree. Después de cualquier cambio de rama:
- Si cambiaron las dependencias del panel: `docker compose restart frontend`.
- Si cambiaron las de la API o hay migraciones: `docker compose up -d --build api migrate scheduler`.
- Antes de dar algo por terminado, verifica https://localhost.

## Convenciones

**Idioma.** Código, tablas, columnas y API en inglés con snake_case; la interfaz, en español
(es-MX).

**Arquitectura.**
- Monolito modular: `app/core` y `app/modules/<dominio>`, con `models`, `schemas`, `service`
  y `router`.
- Los modelos de tabla (`table=True`) se separan de los DTOs.
- La lógica de negocio va en los servicios; los routers orquestan.

**Base de datos.**
- Un esquema por módulo; tablas en plural snake_case.
- PK UUIDv7; `created_at`, `updated_at` y `deleted_at`; FKs e índices con nombre explícito
  (`NAMING_CONVENTION`).
- Excepciones: D-03 (PK bigint en tablas masivas), D-04 (la geografía usa `is_active` +
  `import_run_id`) y D-37 (bitácora append-only).
- Solo Alembic crea tablas; nunca `create_all` fuera de tests.

**API.**
- Versionada en `/api/v1`, con OpenAPI (Swagger y ReDoc, deshabilitables en producción).
- Errores RFC 9457 y paginación por cursor; nada de consultas sin límite.

**Seguridad.**
- Toda consulta aplica el alcance geográfico en SQL, no solo en el endpoint.
- Toda escritura queda en la bitácora: usa el ORM o llama a `record_audit`.
- Los campos sensibles se cifran a nivel aplicación.
- Los secretos solo llegan por variables de entorno (`PAZ_*`).

**Panel.** Solo se usa el cliente generado por Hey API; prohibido escribir `fetch` a mano.
Los permisos nuevos se copian en `frontend/src/lib/auth/permissions.ts`.

**Datos del INE.** No se versionan: `/data/` está en `.gitignore`.

Los detalles y las trampas conocidas están en `docs/architecture.md`.

## Proceso

0. **Las ADR mandan.** Consulta `docs/adr/` antes de cualquier diseño o implementación.
   Registra cada decisión nueva como `D-NN-tema.md`, con el siguiente número, y agrégala al
   índice. Las decisiones no se reescriben: se reemplazan con una nueva que las cite.
1. **Módulo nuevo.**
   - Crea su ficha en `docs/modules/<módulo>.md` a partir de `_TEMPLATE.md`.
   - Señala vacíos e inconsistencias frente a las ADR y los módulos existentes.
   - No redefinas entidades de otros módulos (por ejemplo `Person` o la geografía).
2. **Preguntas.** Haz todas las preguntas de clarificación necesarias antes de escribir
   código. Van de una en una con el selector interactivo, con la opción recomendada primero y
   las abreviaturas electorales explicadas.
3. **Aprobaciones previas.** Propón el modelo de datos (diagrama ER en Mermaid) y el plan por
   fases, y espera aprobación. Si una decisión tiene alternativas relevantes, propón 2
   opciones con sus trade-offs.
4. **Por fases.** Implementa una fase a la vez; no avances sin tests verdes y sin aprobación
   del usuario.
5. **Reglas electorales.** Nunca inventes datos del INE ni reglas electorales. Si una regla no
   está especificada, pregúntala o déjala configurable y documéntala como suposición.
6. **Flujo git.** rama → tests → docs → PR → CI verde → aprobación del usuario →
   `gh pr merge N --squash --delete-branch`.

## Calidad

- **Cobertura:** ≥ 85 % en servicios y validaciones de negocio.
- **Autorización:** tests que prueben explícitamente que un usuario **no** puede acceder fuera
  de su alcance ni sin el permiso.
- **Seeds:** de desarrollo realistas (al menos un estado completo: `./scripts/seed-dev-geo.sh`).
- **Entregables por fase:**
  - código, migraciones y tests verdes;
  - README actualizado y `.env.example` documentado;
  - colección Bruno en `docs/api/`;
  - ficha del módulo y ADR al día.
- **Cierre de fase:** suposiciones, deuda técnica y riesgos en `docs/history/fases/`.
