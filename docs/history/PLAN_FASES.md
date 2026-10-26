# Plan por fases — PAZOS MVP

**Estado:** aprobado el 2026-10-24 (D-42). **Base:** `docs/DECISIONES.md`, `docs/MODELO_DATOS.md` (aprobado, D-41) y `CLAUDE.md`.

Reglas del `<proceso>`: se implementa **una fase a la vez** y no se avanza sin tests verdes y sin aprobación del usuario.

**Entregables de cada fase** (CLAUDE.md §calidad):
- código, migraciones Alembic y tests verdes en CI;
- README actualizado y `.env.example` documentado;
- colección de ejemplos de la API;
- al cerrar: lista de suposiciones, deuda técnica y riesgos;
- las decisiones nuevas se agregan a `DECISIONES.md`.

---

## Ajuste al orden sugerido

CLAUDE.md sugiere el orden *infra → identidad → geografía → candidaturas → panel*. Hay una dependencia que obliga a ajustarlo: el **alcance geográfico** de los usuarios (`user_scopes`, `user_scope_sections`) necesita que las tablas geográficas existan.

**Propuesta:**
- La fase B entrega identidad completa (autenticación, 2FA, sesiones, RBAC y auditoría) **sin** alcance geográfico.
- El alcance se conecta al final de la fase C, cuando ya existe la geografía, con sus tests negativos ("un usuario NO puede ver fuera de su alcance").

El orden general no cambia.

**Personas (`people`)** se implementa en la fase D, junto con candidaturas, que es su primer consumidor.

---

## Fase A — Infraestructura base, core y CI

**Repositorio y entorno**
- Estructura del monorepo: `backend/` (uv, Python 3.12+), `frontend/` (pnpm), `infra/`, `docs/`.
- Docker Compose para desarrollo: `api`, `db` (PostgreSQL 18 + PostGIS), `redis`, `frontend`, `caddy` (TLS local), `mailpit`.
- Dockerfiles multi-stage de producción.

**Backend core (`app/core`)**
- App factory de FastAPI con `/api/v1`, Swagger UI y ReDoc deshabilitables por configuración.
- Configuración con `pydantic-settings`, solo por variables de entorno.
- Logs JSON con structlog y `request_id` por request; OpenTelemetry (trazas y métricas) con exportador configurable.
- Errores uniformes RFC 9457 (Problem Details).
- CORS restrictivo y cabeceras de seguridad.
- Engine async (SQLAlchemy 2 + asyncpg) y unidad de trabajo por request.
- Base de modelos SQLModel: mixins de UUIDv7 y timestamps, y `naming_convention` de constraints.
- Alembic: esquemas `identity`, `geography`, `people`, `candidacies`, `audit` y extensiones `postgis`, `pg_trgm`, `unaccent`, `citext`.
- Cliente Redis.
- Criptografía (D-31, D-32): `KeyProvider` con implementación por variable de entorno, AES-256-GCM con cifrado de sobre, HMAC para blind index y `key_version`.
- Bitácora (D-37): tabla `audit.audit_log` particionada por mes, rol de solo inserción, trigger anti-UPDATE/DELETE, cadena de hashes, hook de escritura en la unidad de trabajo y comando `verify-audit-chain`.
- Endpoints `/health` (vivo) y `/ready` (BD + Redis).
- Paginación por cursor genérica y helpers de filtros y orden.

**Frontend base**
- Vite + React 19 + TypeScript strict, TanStack Router (SPA), TanStack Query, Tailwind 4 + shadcn/ui y Biome.
- Script de generación del cliente con Hey API (SDK + hooks de Query + Zod) desde el OpenAPI.
- Vitest + Testing Library y Playwright con un smoke test.

**CI (GitHub Actions)**
- Filtros por ruta (`backend/**`, `frontend/**`).
- Backend: ruff, mypy strict y pytest con testcontainers (PostGIS real).
- Frontend: Biome, `tsc`, Vitest y build.
- Build de imágenes.
- Verificación de que el cliente generado esté al día con el OpenAPI.

**Verificación externa:** confirmar PG18 + PostGIS en Postgres administrado de DigitalOcean y AWS (D-05). Si no hay, aplicar el fallback a PG17.

**Criterios de aceptación**
- `docker compose up` levanta todo y `/ready` responde 200.
- CI verde.
- Tests de core: Problem Details, cifrado y descifrado con rotación de llave, cadena de auditoría (incluido que detecte una alteración), paginación por cursor.

---

## Fase B — Identidad (sin alcance geográfico)

**Modelos:** usuarios, invitaciones, tokens de reset, credenciales TOTP, códigos de recuperación, sesiones, refresh tokens, roles, permisos y sus tablas puente.

**Autenticación**
- Login con email + contraseña (Argon2id con parámetros configurables).
- Bloqueo por intentos fallidos; rate limiting por IP y por usuario en Redis.
- Access token JWT de vida corta.
- Refresh token rotativo en cookie `httpOnly; Secure; SameSite=Strict`, con **detección de reuso**: si se reusa un token, se revoca la familia completa.
- Sesiones por dispositivo: listar, revocar una y cerrar todas. La revocación se refleja de inmediato vía Redis.

**2FA**
- TOTP RFC 6238 (pyotp): enrolamiento con QR, confirmación y anti-replay (`last_used_step`).
- 10 códigos de recuperación de un solo uso.
- TOTP obligatorio según `roles.requires_mfa`: un usuario sin enrolar solo puede acceder al flujo de enrolamiento.

**Altas y contraseñas**
- Alta solo por invitación (D-35), con correo SMTP (Mailpit en desarrollo).
- Aceptar invitación, recuperar contraseña y cambiar contraseña.

**Autorización:** RBAC con dependencia `require_permission("module.action")`. Seeds de los 5 roles (D-33) y del catálogo de permisos.

**Auditoría:** todas las escrituras de identidad y los eventos de seguridad (login, logout, MFA, bloqueo, revocación) quedan en la bitácora.

**API:** CRUD de usuarios, roles, permisos y asignación de roles, más consulta paginada de la bitácora.

**Criterios de aceptación**
- Tests de cada flujo de autenticación, incluidos los negativos: TOTP inválido o reusado, refresh reusado, cuenta bloqueada, invitación expirada.
- Tests de autorización por permiso.
- Cobertura ≥ 85 % en servicios.

---

## Fase C — Geografía + alcance geográfico

**Modelos y migraciones:** marcos, importaciones y sus errores, circunscripciones, estados, municipios, DF, DL, secciones, `section_parts`, localidades, `locality_sections`, manzanas (particionadas por marco), colonias, `neighborhood_sections` y catálogos de códigos.

**Descargador INE (D-16)**
- Consulta el índice público (`/sige8/api/bases`, `/api/catalogos`).
- Descarga los 7z de la BGD y los catálogos, con hash SHA-256 y caché local.

**Importador (D-18)**, como CLI (`paz geo import --framework … --state 01 --dry-run`):
- Lectura con pyogrio, encoding por `.cpg` o CP1252, mapeo por nombre de campo, reproyección a 4326 y promoción a Multi*.
- Validación por registro (padre inexistente, geometría inválida —se repara con `ST_MakeValid` y se reporta—, manzana fuera de su sección, códigos sin catálogo).
- `COPY` a una tabla temporal y upsert por llave natural, conservando los IDs. Lo que desaparece del origen se marca `is_active = false`.
- Pasos derivados: geometría de circunscripciones (`ST_Union`), `section_parts` (`ST_Subdivide`), `neighborhood_sections` con umbral configurable (D-09) y descripciones de catálogos desde los catálogos INE (D-15).
- Reporte por ejecución en `import_runs` / `import_errors` y una entrada de bitácora por ejecución.
- Activación de marco con remapeo por llave natural (D-41 punto 7). En el MVP solo existe un marco, pero el flujo queda probado.

**API**
- Jerarquía: hijos y ancestros de cualquier nodo.
- Búsqueda por clave INE flexible y por nombre (trigramas).
- Punto-en-polígono → sección, municipio, DL, DF, estado y circunscripción.
- Vector tiles MVT por nivel con simplificación por zoom y caché en Redis.
- Consulta de corridas de importación y su reporte.

**Alcance geográfico (lo que se movió de la fase B)**
- `user_scopes` con CHECK por nivel y CRUD de alcances.
- Recálculo de `user_scope_sections`.
- Filtro por alcance en la **capa de repositorio**, aplicado a toda consulta de geografía.

**Datos:** seed de Aguascalientes descargado por script (D-20); los datos nunca entran a git.

**Criterios de aceptación**
- La importación de Aguascalientes es idempotente: la segunda corrida da 0 insertados y 0 actualizados, con los mismos IDs. El dry-run no escribe nada.
- Conteos contra el origen y validaciones de `DISENO_BD_GEOESPACIAL.md` §5.
- Tests negativos de alcance: un usuario de un DF no ve secciones de otro DF ni accede a ellas.
- **Benchmark nacional**, fuera de CI y documentado en el README: carga de los 32 estados, punto-en-polígono < 50 ms p95 y lecturas < 200 ms p95 con ~73 mil secciones y 2.5 M de manzanas.

---

## Fase D — Personas y candidaturas

**Personas (`people`)**
- Persona con CURP cifrada + blind index.
- Validador de CURP: estructura, dígito verificador y coherencia con fecha, sexo y entidad, con override por permiso (D-30).
- Contactos y domicilios cifrados; la geografía del domicilio queda en claro.
- Consentimientos de privacidad, soft-delete y `purge_after` con un comando de purga programable.
- Autocompletado por nombre.

**Candidaturas**
- Catálogos: partidos y cargos. Seed de los cargos de `MODELO_DATOS.md` §4, Senado y Presidencia incluidos (D-22).
- Procesos electorales y módulo de configuración electoral (D-23):
  - cargos habilitados, posiciones y método de RP local (D-21);
  - composición de planilla mediante `slate_parent_office_type_id`;
  - configuración por municipio (régimen, regidurías MR/RP, sindicaturas) con captura masiva por estado.
- Coaliciones y candidaturas comunes.
- Postulaciones y fórmulas: creación según el tipo (cargo único, planilla o lista), generación de posiciones según la configuración, propietario y suplente obligatorios.
- Estatus con historial (`aspirant → registered → approved | substituted | cancelled`) y sustitución con fórmula nueva ligada (D-29).
- Motor de validaciones (D-28): las 4 reglas, parametrizables por proceso y cargo, bloqueantes o como advertencia, con overrides auditados. Por defecto solo está activa "persona no duplicada".
- Alcance: edición si la geografía de la postulación queda contenida por completo en el alcance del usuario; solo lectura si únicamente se traslapa (D-34).

**API:** CRUD completo de todo lo anterior, más endpoints de acción (cambiar estatus, sustituir, validar postulación).

**Criterios de aceptación**
- Tests de cada regla de validación con sus parámetros.
- Tests de sustitución e historial.
- Tests de unicidad de CURP y de cifrado (que nada sensible quede en claro en la BD ni en la bitácora).
- Tests negativos de alcance para edición y lectura.
- Cobertura ≥ 85 % en servicios y validaciones.

---

## Fase E — Panel de administración

**Base**
- Pantallas de autenticación: login, enrolamiento TOTP, códigos de recuperación, aceptar invitación y recuperar contraseña.
- Layout con navegación según permisos.
- Componentes genéricos: tabla con paginación por cursor del lado del servidor, filtros, orden y búsqueda; formularios con TanStack Form + esquemas Zod generados; **navegación completa con teclado** y atajos.

**Pantallas**
- **Geografía:** explorador jerárquico, búsqueda por clave o nombre, **visor de mapa** (MapLibre + MVT) y consulta de corridas de importación con su reporte.
- **Identidad:** usuarios, invitaciones, roles, permisos, alcances, sesiones activas y consulta de la bitácora.
- **Personas:** CRUD con autocompletado y validación de CURP en línea.
- **Candidaturas:**
  - configuración del proceso;
  - editor de planillas y listas optimizado para captura (teclado primero, autocompletado de personas y geografía);
  - flujo de sustitución;
  - avisos de validación en línea.

**Criterios de aceptación**
- Playwright end-to-end de los flujos principales: login con TOTP, captura de una planilla completa, sustitución, usuario con alcance limitado.
- Vitest en componentes y hooks.
- Accesibilidad básica de teclado verificada.

---

## Decisiones a confirmar con este plan

1. **Orden ajustado:** el alcance geográfico se conecta al final de la fase C.
2. **Personas en la fase D**, junto con candidaturas.
3. **Importaciones por CLI**: en el MVP el panel solo consulta las corridas, no las lanza. Lanzar importaciones desde el panel requiere un worker de tareas en segundo plano, que se propone para después.
4. **Colección de ejemplos de la API:** **Bruno** (archivos de texto versionables en git) en `docs/api/`. Alternativa: colección de Postman exportada.
5. **Benchmark nacional fuera de CI:** el CI usa Aguascalientes; el benchmark con los 32 estados se corre manualmente al cerrar la fase C y sus resultados se documentan.
