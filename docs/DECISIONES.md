# Registro de decisiones — PAZOS MVP

**Fecha:** 2026-10-24 · **Origen:** paso 2 del `<proceso>` de `CLAUDE.md` (preguntas de clarificación).
**Precedencia:** cuando este documento contradice a `CLAUDE.md` o a `DISENO_BD_GEOESPACIAL.md`, manda este documento. Cada decisión nueva se agrega al final con el siguiente número; no se reescriben decisiones pasadas, se reemplazan con una nueva que las cite.

Formato: **D-NN · Tema** — decisión. *Motivo.* (Alternativas descartadas.)

---

## 1. Geografía electoral

**D-01 · Marco geográfico.** Hay un único marco geográfico **nacional activo** (nombre, fecha de corte y acuerdo INE). Los marcos anteriores se conservan como históricos de solo lectura.
*Motivo:* simplicidad de consulta; la redistritación del INE es nacional. (Descartado: un marco por estado, o marcos federal y local separados.)

**D-02 · Recarga.** Recargar datos de un marco existente es un **upsert por llave natural que conserva los IDs**. Un marco nuevo solo se crea cuando hay redistritación.
*Motivo:* candidaturas, alcances de usuario y personas referencian nodos geográficos; regenerar IDs rompería esas referencias. (Descartado: un marco nuevo por cada importación.)

**D-03 · PK híbrida (excepción a CLAUDE.md).** UUIDv7 en las entidades que otras tablas referencian (circunscripción, estado, municipio, distritos, sección, localidad, colonia). `bigint` en tablas masivas que nadie referencia (manzanas, puntos localidad-sección, partes de sección, errores de importación).
*Motivo:* con 2.5 M de manzanas por marco, un UUID duplica el tamaño de índices y FKs sin ningún beneficio. (Descartado: UUIDv7 en todo.)

**D-04 · Geografía de solo lectura (excepción a CLAUDE.md).** Las tablas geográficas solo cambian por importación. Llevan `created_at`, `updated_at`, `import_run_id` e `is_active`, y **no llevan `deleted_at`**: lo que desaparece del origen se marca `is_active = false`.
*Motivo:* el soft-delete no tiene sentido en datos de referencia oficiales. (Descartado: las tres columnas en todo; geografía editable desde el panel.)

**D-05 · PostgreSQL 18 + PostGIS 3.5+.** Se usa `uuidv7()` nativo.
*Riesgo:* hay que verificar que el Postgres administrado de DigitalOcean y el de AWS ofrezcan PG18 con PostGIS. *Alternativa:* PG17 con UUIDv7 generado en la aplicación, sin otro impacto.

**D-06 · Modelo conceptual (corrige la jerarquía de CLAUDE.md).**
- La **sección** es la unidad atómica del marco electoral.
- **Distrito federal (DF)**, **distrito local (DL)** y **municipio** son agrupaciones de secciones **independientes entre sí**: se traslapan y ninguna está anidada dentro de otra. Cada sección pertenece a exactamente un DF, un DL y un municipio.
- **Estado** contiene DF, DL y municipios. **Circunscripción** contiene estados.
- **Manzana, colonia y localidad** son geografía **tradicional** (no electoral) y se relacionan con la sección:
  - La manzana se liga a **una** sección por la clave que trae la BGD. Sus distritos se obtienen siempre a través de la sección y **no se guardan en la manzana**. Una manzana que geométricamente cae fuera de su sección solo genera una advertencia en el reporte.
  - La colonia se relaciona **N:M** con las secciones (ver D-09).

**D-07 · Circunscripción.** La asignación estado → circunscripción se toma del campo `ENTIDAD.circunscri` de cada marco. La geometría se calcula al importar como `ST_Union` de los estados.

**D-08 · Diputaciones locales de RP.** **No se modelan circunscripciones plurinominales locales.** La RP local se configura por estado y proceso con uno de tres métodos (ver D-21).

**D-09 · Relación colonia ↔ sección.**
- **Colonias con polígono:** se relacionan con una sección si la intersección supera un **umbral configurable** (por defecto 5 % del área de la colonia o 500 m²). Se guardan el % y el área de traslape.
- **Colonias puntuales:** se relacionan con la sección que contiene el punto.
- **Sin geometría (596):** se conservan con `geom NULL`, sin relación espacial, y se reportan (D-12).

**D-10 · Llave natural de colonia.** Se usa `(estado, municipio, ID de origen BGD)` si se comprueba que el ID es estable entre descargas. Si no lo es, se usa `(estado, municipio, nombre normalizado, cp, representación)` con detección de duplicados. *Pendiente:* verificarlo con dos cortes distintos.

**D-11 · Localidades.** Entran al MVP con dos capas:
- `localities`: una fila por localidad, con el polígono de LIMITE_LOCALIDAD (NULL si la localidad solo existe como punto).
- `locality_sections`: los puntos de LOCALIDAD, uno por cada par localidad-sección.

**D-12 · Registros sin geometría.** Se conservan con `geom NULL` y aparecen en el reporte de importación.

**D-13 · Capas no electorales fuera del MVP.** Vialidades, carreteras, POI, hidrografía, litoral, módulos/vocalías INE y números exteriores quedan para un módulo futuro, `cartography`, que se agregará como paquete sin tocar el núcleo. `DISENO_BD_GEOESPACIAL.md` §3.3–3.6 se conserva como referencia para ese módulo.

**D-14 · Particionado.** `geography.blocks` (manzanas) se particiona por lista de `framework_id`, una partición por marco.

**D-15 · Catálogos de códigos.** Las descripciones se derivan de los **catálogos oficiales del INE**, cruzándolos con la BGD, y se guarda la fuente. Un código sin evidencia queda con descripción `NULL`, editable desde el panel. No se inventan significados.
Mapeos verificados con Aguascalientes (corte dic-2025), con coincidencia del 100 % registro por registro:

| Campo BGD | Código → texto INE | Evidencia |
|---|---|---|
| `SECCION.tipo` | 2 → URBANO(A), 3 → MIXTO(A), 4 → RURAL | 736/736 vs Catálogo de Secciones |
| `MANZANA.status` | 1 → `C`, 2 → `*` | 25,482/25,482 vs Catálogo de Manzanas |
| `LOCALIDAD.tipo` | 4 → RURAL | 1,729/1,729 vs Catálogo de Localidades con Sección |

Pendiente: el significado de `C` y `*` (el Catálogo de Productos Cartográficos habla de "habilitada / deshabilitada", pero no dice cuál es cuál) y el código 2 de localidad (presumiblemente URBANO).

**D-16 · Fuente de datos del primer marco.** Se usa la **descarga oficial vigente del INE**, con un mismo corte para los 32 estados:
- BGD: corte del 15 de diciembre de 2025, `https://storage.googleapis.com/mapoteca/BGD_15_diciembre_2025/04 SHAPEFILE_EXTERNOS SIN NUMEXT/NN ESTADO.7z`.
- Catálogos: corte del 19 de enero de 2026, `https://storage.googleapis.com/mapoteca/CORTE_19ENE2026_PRODUCTOSCARTOGRAFICOS/CATALOGOS/...`.
- Índice de archivos: API pública `https://cartografia.ine.mx/sige8/api/bases` y `/api/catalogos`, que alimentan la página `productosCartograficos/bases`.

Esto también resuelve que la carpeta local de Baja California viniera de otra descarga. Las carpetas locales quedan solo como referencia.

**D-17 · KML fuera del MVP.** El usuario se encarga de extraer la geometría de los KML que tiene. El importador se diseña con una interfaz de "fuente" para agregar formatos después.

**D-18 · Importador.** Python + **pyogrio**:
- Lee los 7z/shapefiles y los catálogos (txt/xlsx).
- Normaliza cada registro: encoding según `.cpg` o CP1252, `SIN NOMBRE` → NULL, mapeo por nombre de campo, reproyección a EPSG:4326 y `PROMOTE_TO_MULTI`.
- Valida registro por registro.
- Carga con `COPY` a una tabla temporal y hace **upsert por llave natural**.
- Modo `--dry-run`, reporte de errores y advertencias por registro (`import_errors`) e idempotencia (archivo + hash SHA-256).

(Descartado: ogr2ogr + SQL, porque solo reporta errores por lote y depende del binario de GDAL.)

**D-19 · API geográfica.**
- **Búsqueda por clave INE flexible:** acepta formatos con o sin ceros y separadores (`09-0123`, `9 123`, `090123`; municipio `09-005`; distrito `09-12`). Se normaliza a (estado, clave) y se puede filtrar por nivel. También hay búsqueda por nombre con `pg_trgm` + `unaccent`.
- **Punto-en-polígono:** se resuelve sobre `section_parts` (secciones subdivididas con `ST_Subdivide`) y luego se suben los ancestros por FK, para cumplir < 50 ms p95.
- **Vector tiles:** endpoint MVT (`/api/v1/geography/tiles/{level}/{z}/{x}/{y}.mvt`) con `ST_AsMVT`, simplificación por zoom y caché en Redis. El panel incluye un **visor de mapa básico** (MapLibre GL).

**D-20 · Datos de desarrollo y CI.** Aguascalientes: 736 secciones y ~25 mil manzanas. Un script lo descarga del INE; los datos no se versionan en git.

## 2. Candidaturas

**D-21 · RP local configurable.** Por estado y proceso se elige el método de asignación:
- `closed_list`: lista cerrada de "pluris".
- `best_loser`: mejor perdedor preponderante, que sale de quienes compitieron por mayoría relativa.
- `mixed`: combinación de ambos, con regla de intercalado configurable.

Cuando el método lo requiere, se registra una lista cerrada estatal con el número de posiciones configurado.

**D-22 · Senado y Presidencia (amplía el alcance).**
- **Senaduría de MR:** por estado, una lista de **2 fórmulas con posición** (1 y 2). La posición 1 del partido que queda en segundo lugar entra por **primera minoría**.
- **Senaduría de RP:** **lista nacional cerrada de 32 fórmulas**.
- **Presidencia de la República:** ámbito nacional.

Las tres quedan construidas en el modelo, la API y la UI genérica.

**D-23 · Módulo de configuración electoral.** Por cada proceso se habilita qué cargos van a elección, a nivel federal y a nivel local (por estado). También guarda el número de posiciones, el método de RP (D-21) y la configuración municipal (D-24 a D-26).

**D-24 · Regidurías.** Cada regiduría tiene posición y principio (MR en planilla, RP en lista). El número de cada tipo se configura **por municipio y proceso**, capturado en el panel o importado de un archivo. No se precargan números.

**D-25 · Sindicatura.** Por estado y proceso se configura si la sindicatura va **en la planilla o por separado**, y cuántas hay. No se precarga ningún estado; queda documentado como suposición.

**D-26 · Régimen municipal.** Cada municipio tiene, por proceso, un régimen de elección: `party_based` o `normative_system` (sistemas normativos internos). Los de sistemas normativos se excluyen de las planillas. Las alcaldías de CDMX usan el mismo modelo de planilla, con cargos propios del catálogo (alcaldía + concejalías). Nada se precarga sin fuente oficial.

**D-27 · Partidos y alianzas.** El modelo soporta cualquier partido, coalición o candidatura común. En el MVP la UI solo opera las candidaturas **de PAZ y sus alianzas**; las de partidos rivales llegan en una fase posterior.

**D-28 · Motor de validaciones.** Cada regla (paridad de género, alternancia en listas, suplente del mismo género, persona no duplicada en el proceso) se parametriza por estado y proceso: activa/inactiva, bloqueante o solo advertencia, y parámetros. Por defecto **solo está activa "persona no duplicada"**.

**D-29 · Sustitución.** La fórmula original pasa a `substituted` y se crea una **fórmula nueva en la misma posición**, ligada a la anterior y con su motivo. Se puede sustituir solo al suplente o a ambos integrantes; el historial completo de cada posición queda consultable.

## 3. Persona y datos sensibles

**D-30 · Validación de CURP.** Se valida:
- La estructura oficial.
- El dígito verificador.
- La **coherencia** con fecha de nacimiento, sexo y entidad de nacimiento capturados. Una incoherencia es una advertencia que un usuario con permiso puede forzar.

No hay integración con RENAPO.

**D-31 · Cifrado a nivel aplicación.**
- **Cifrados:** CURP, teléfonos, correos de contacto y domicilio, con AES-256-GCM.
- **Blind index:** la CURP lleva un hash HMAC-SHA256 para la unicidad y la búsqueda exacta; los teléfonos, uno para la búsqueda exacta.
- **En claro:** el nombre, para el autocompletado con trigramas, y la geografía del domicilio (estado, municipio, sección, colonia, localidad) junto con el CP.

**D-32 · Gestión de llaves.** Interfaz `KeyProvider` con **cifrado de sobre** (envelope). En desarrollo, llave maestra por variable de entorno; en producción, KMS (AWS KMS como destino probable) sin cambiar código. Cada registro cifrado guarda `key_version` para poder rotar.

## 4. Identidad, acceso y auditoría

**D-33 · Roles iniciales.** Configurables desde el panel. Se precargan:
- `superadmin`: todo, sin alcance.
- `admin`: usuarios y catálogos dentro de su alcance.
- `coordinator`: CRUD de candidaturas en su alcance.
- `capturist`: crea y edita sin aprobar.
- `viewer`: solo lectura.

**TOTP obligatorio** para superadmin, admin y coordinator.

**D-34 · Alcance geográfico.**
- El alcance de un usuario se traduce en el **conjunto de secciones** de sus nodos asignados (tabla derivada `user_scope_sections`).
- **Geografía:** ve todo lo que toca esas secciones.
- **Candidaturas:** **edita** las cuya geografía queda contenida por completo en su alcance, y ve **en solo lectura** las que solo se traslapan.
- Estado y circunscripción contienen todo lo de abajo.
- El filtro se aplica en la capa de repositorio (consulta), no solo en los endpoints.

**D-35 · Alta de usuarios y correo.** Las altas son **solo por invitación** de un admin; no hay registro público. El envío es por SMTP configurable (SES, SendGrid, Postmark, Workspace…) y en desarrollo se usa Mailpit.

**D-36 · Auditoría de importaciones.** Se audita **por ejecución** (`import_runs`): quién, cuándo, archivo y su hash, corte, conteos y reporte por registro. Las filas importadas apuntan a su `import_run`. No hay entrada de bitácora por fila.

**D-37 · Bitácora inmutable.** Tabla **append-only** particionada por mes y escrita con un rol de BD que solo puede hacer `INSERT` (sin UPDATE ni DELETE, reforzado con trigger). Cada entrada guarda el **hash de la anterior** (cadena verificable con un comando). Los meses viejos se pueden exportar a almacenamiento externo. Los valores sensibles en `before`/`after` se guardan enmascarados o cifrados.

## 5. Infraestructura y repositorio

**D-38 · Despliegue.** Arranca en **DigitalOcean** con alta probabilidad de migrar a **AWS**. Todo se mantiene portátil: contenedores estándar, almacenamiento compatible con S3, sin servicios propietarios en el núcleo. **Caddy** es el proxy inverso.

**D-39 · Monorepo.** Este repositorio contiene `backend/` (uv), `frontend/` (pnpm), `infra/` (Compose, Caddy) y `docs/`. El CI corre por carpeta según lo que cambió.

**D-40 · Cliente de API.** **Hey API** (`@hey-api/openapi-ts`) con los plugins de TanStack Query y Zod.

## 6. Modelo de datos

**D-41 · Modelo de datos aprobado.** El usuario aprobó `docs/MODELO_DATOS.md` el 2026-10-24, incluidos sus 7 puntos:
1. Módulo `people` separado de `candidacies`.
2. Enumeraciones como `text + CHECK`.
3. Postulación + fórmula como estructura única para todos los cargos, con la composición de planillas en `slate_parent_office_type_id`.
4. `section_parts` para el punto-en-polígono.
5. `user_scope_sections` como conjunto derivado para filtrar por alcance.
6. `framework_id` en todas las tablas geográficas, con FKs compuestas.
7. Remapeo por llave natural de alcances y domicilios al activar un nuevo marco.

**D-42 · Plan por fases aprobado.** El usuario aprobó `docs/PLAN_FASES.md` el 2026-10-24, incluidos sus 5 puntos:
1. El alcance geográfico se conecta al final de la fase C.
2. Personas se implementa en la fase D.
3. Las importaciones se lanzan por CLI; el panel solo las consulta.
4. Colección de ejemplos de la API con Bruno en `docs/api/`.
5. El benchmark nacional se corre fuera de CI.

## 7. Fase A — implementación

**D-43 · Imagen propia de PostgreSQL 18 + PostGIS.** `infra/db/Dockerfile` parte de `postgres:18-bookworm` (multi-arquitectura) e instala PostGIS 3 desde PGDG.
*Motivo:* la imagen oficial `postgis/postgis:18-3.6` solo existe para amd64; en Macs arm64 correría emulada. La misma imagen sirve para desarrollo, CI (testcontainers) y como referencia de producción.

**D-44 · Separación de roles de base de datos.** Las migraciones corren con el rol **dueño** (`PAZ_MIGRATIONS_DATABASE_URL`). La API se conecta con un rol de **mínimo privilegio** (`paz_app`), que solo recibe los GRANT que emiten las migraciones:
- DML en los esquemas de módulo;
- en `audit`, solo `SELECT` y `EXECUTE` de `append_entry` / `verify_chain`.

*Motivo:* la inmutabilidad de la bitácora y el principio de mínimo privilegio (ASVS nivel 2).

**D-45 · Implementación de la bitácora (detalla D-37).**
- La cadena de hashes se calcula **dentro de PostgreSQL**, en la función `audit.append_entry` (`SECURITY DEFINER`).
- Una fila `audit.chain_head` bloqueada con `FOR UPDATE` serializa los eslabones hasta el commit del llamador.
- Triggers rechazan `UPDATE`, `DELETE` y `TRUNCATE` incluso para el dueño.
- `verify_chain` detecta filas alteradas, huecos y cola truncada.
- Las escrituras del ORM se auditan automáticamente (`AuditedSession`, hook `after_flush`); las sentencias Core no pasan por el hook y deben usar `record_audit`.

*Costo conocido:* el bloqueo es un punto de contención global; se mide en las pruebas de carga de las fases C y D.

**D-46 · Convenciones de API.**
- Los errores son RFC 9457 con `type = urn:pazos:problem:<code>` y las extensiones `code` y `request_id`, servidos como `application/problem+json` (también en el OpenAPI, así que el cliente generado los tipa como `Problem`).
- `/health` y `/ready` quedan fuera de `/api/v1`.
- El `X-Request-ID` entrante se respeta si es válido; si no, se genera uno.
- Las variables de entorno del backend llevan el prefijo `PAZ_`.

**D-47 · TypeScript 6 en el frontend.** Hey API (0.99) usa la API de compilador de TypeScript en JavaScript, que TypeScript 7 (nativo) ya no expone. Se fija `typescript@^6` hasta que Hey API soporte la versión 7 (deuda técnica).

## 8. Fase B — identidad

**D-48 · Tokens y sesiones.**
- **Access token:** JWT HS256 de 15 min. Viaja en `Authorization: Bearer` y el panel lo guarda solo en memoria. Lleva el id de sesión (`sid`) y el alcance (`scope`).
- **Refresh token:** opaco, de 256 bits, rotativo. Solo se guarda su SHA-256. Viaja en una cookie `paz_refresh` (`HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`) y, como defensa adicional, se verifica el `Origin`.
- **Reuso:** presentar un refresh token ya usado o revocado revoca la sesión completa y se audita como `refresh_reuse_detected`.
- **Duración de la sesión:** 7 días de inactividad máxima y 30 días de vida absoluta.
- **Revocación inmediata:** cada request carga usuario y sesión en una consulta (sesión viva, usuario activo). Esto reemplaza la marca en Redis que mencionaba el plan: es igual de inmediato y no depende de que Redis conserve datos.
- **Reto de MFA:** JWT de 5 min.
- **Alcance `mfa_enrollment`:** si el rol exige 2FA y el usuario no ha enrolado TOTP, solo puede usar los endpoints de enrolamiento, perfil y logout.

**D-49 · Defensa del login.**
- **Respuesta única:** todo fallo devuelve el mismo 401 genérico; el motivo solo queda en la bitácora (`login_failed`). Cuando la cuenta no existe se verifica un hash ficticio, para que el tiempo de respuesta no lo delate.
- **Bloqueo:** 5 intentos fallidos (contraseña, TOTP o código de recuperación) bloquean la cuenta 15 min.
- **Rate limiting** (ventana fija en Redis):

  | Endpoint | Límite |
  |---|---|
  | Login, por IP | 20/min |
  | Login, por correo | 10/15 min |
  | MFA, por usuario | 5/5 min |
  | Restablecer contraseña, por correo | 5/h |

- **Sin enumeración:** `password/forgot` siempre responde 202.

**D-50 · Contraseñas.**
- Argon2id (t=3, m=64 MiB, p=4) con rehash transparente al iniciar sesión.
- Política por longitud (12–128) sin reglas de composición (NIST 800-63B). Rechaza contraseñas repetitivas o que contengan el correo.
- El cotejo contra contraseñas filtradas (ASVS 2.1.7) queda como deuda.

**D-51 · Segundo factor.**
- **TOTP:** RFC 6238 (SHA-1, 6 dígitos, 30 s, tolerancia de ±1 paso) con anti-replay por paso (`last_used_step`). El secreto, de 160 bits, se cifra con `FieldCipher` (contexto `identity.totp_credentials.secret`).
- **QR:** se genera en el backend como data URI SVG.
- **Códigos de recuperación:** 10 de un solo uso, de 80 bits, guardados con HMAC (no Argon2: su entropía lo permite y verificarlos sale barato).
- **Desactivar TOTP** requiere contraseña + código y no se permite si el rol exige 2FA.
- **Reset administrativo:** borra el TOTP y cierra las sesiones del usuario.

**D-52 · Reglas de RBAC.**
- **Superadmin:** `roles.grants_all` concede todos los permisos y lo exime del alcance geográfico.
- **Sin escalamiento:** solo se pueden asignar roles y otorgar permisos que uno mismo tiene.
- **Cuentas superadmin:** solo otro superadmin puede gestionarlas, y no se puede desactivar ni degradar al último.
- **Roles protegidos:** los de sistema no se eliminan, el de superadmin es inmutable y un rol con usuarios no se puede eliminar.
- **Permisos:** se registran en código (`Perm`) y se siembran por migración; un test detecta si código y base divergen.

**D-53 · Ajustes a la auditoría automática (detalla D-45).**
- `refresh_tokens` y `recovery_codes` no se auditan fila por fila: son secretos de alta rotación. Sus eventos se auditan explícitamente: `login_succeeded`, `login_failed`, `account_locked`, `refresh_reuse_detected`, `logout`, `password_changed`, `password_reset_requested`, `mfa_enrolled`, `mfa_disabled`, `mfa_reset` y `recovery_codes_regenerated`.
- `__audit_ignore_fields__` evita registrar actualizaciones que solo tocan campos de bitácora interna (`user_sessions.last_seen_at`, `ip_address`).

**D-54 · Ajustes al modelo de identidad (sobre `MODELO_DATOS.md` §2).**
- Columnas nuevas: `roles.grants_all`, `user_sessions.auth_methods` (valores RFC 8176) y `user_invitations.revoked_at`.
- El usuario invitado existe con `status = invited` y sin contraseña hasta aceptar la invitación.

**D-55 · Correo y arranque.**
- **Correo:** el backend puede ser `smtp`, `console` o `memory`. Los correos salen en segundo plano después del commit. Los enlaces apuntan a rutas del panel que se construyen en la fase E (`/aceptar-invitacion`, `/restablecer-contrasena`).
- **Primer superadmin:** se crea con `paz users create-superadmin` y debe enrolar TOTP en su primer acceso.

**D-56 · Fase B aprobada.** El usuario aprobó la fase B el 2026-10-24; PR #2 fusionado a `main`.

## 9. Fase C — geografía

**D-57 · Relación colonia ↔ sección desde el catálogo del INE (reemplaza D-09).**
- El Catálogo de Colonias del INE (corte ene-2026) publica la relación oficial colonia–sección con el mismo `ID` que la BGD. Verificado en Aguascalientes: 2,189 pares, 1,265 colonias, 100 % de coincidencia por `ID`, nombre y `CONTROL`.
- **Fuente principal:** el catálogo (`source = 'ine_catalog'`).
- **Cálculo espacial:** sirve para tres cosas:
  - el % y el área de traslape de cada par;
  - agregar pares para colonias que el catálogo no cubra (`source = 'computed'`, con el umbral de D-09);
  - reportar en el importador los pares del catálogo sin intersección geométrica.

**D-58 · Verificaciones sobre la llave de colonia (actualiza D-10) y fuentes del importador.**
- **Llave de colonia:** en la BGD dic-2025, `COLONIA.ID` y `CONTROL` son únicos por estado y coinciden con el catálogo. En cambio, `(municipio, nombre, CP)` tiene 18 duplicados en Aguascalientes, así que **no sirve como llave**. Se usa `(estado, ID)`. La estabilidad del `ID` entre cortes sigue sin verificarse, porque solo hay un corte disponible; el importador reporta las colonias cuyo `ID` cambia de nombre o municipio.
- **Carpetas locales:** las de `paz-maps/` son **idénticas byte por byte** a la BGD oficial dic-2025 (verificado en las 9 capas del MVP de Aguascalientes).
- **Fuentes que acepta el importador:** una carpeta de shapefiles o el 7z oficial. Los catálogos tabulares (Secciones, Manzanas, Localidades con Sección, Colonias) se descargan del INE con `paz geo download`.

**D-59 · Mapeos de códigos verificados (amplía D-15).**
- `COLONIA.CLASIFICAC` → tipo de colonia del catálogo. En Aguascalientes: 1 COLONIA, 2 FRACCIONAMIENTO, 3 UNIDAD HABITACIONAL, 4 CONJUNTO HABITACIONAL, 6 RANCHO, 7 BARRIO, 8 EJIDO, 13 CONDOMINIO, 17 FRACCION, 18 GRANJA, 24 RINCONADA, 26 SECTOR, 31 ZONA INDUSTRIAL, 32 ZONA MILITAR, 35 LOCALIDAD.
- Localidades: las 46 de tipo 2 tienen polígono, pero no punto, y concentran las manzanas.

**D-60 · Ajustes de implementación de la geografía (sobre `MODELO_DATOS.md` §1).**
- **Importaciones:**
  - `import_errors` se llama `import_issues`, porque guarda errores y advertencias.
  - `import_runs.counts` (jsonb por tabla) reemplaza las columnas de conteo.
  - `triggered_by` es texto: hoy las importaciones se lanzan por CLI (D-42).
- **Relación colonia–sección:** `neighborhood_sections.source` reemplaza a `match_method` (D-57).
- **Particiones de manzanas:** la función `geography.ensure_block_partition(framework_id)` crea una partición por marco al importar. Alembic las ignora (`env.py`).
- **Upserts:** distinguen insertado de actualizado con `RETURNING old.id IS NULL` (PostgreSQL 18), que funciona también sobre la tabla particionada.
- **Desactivación:** solo se marcan inactivos registros de capas que cargaron sin errores. Si una capa trae errores, se omite la desactivación y se avisa con `deactivation_skipped`, para que un archivo dañado nunca desactive datos válidos.
- **Alcance vacío:** un usuario sin alcance no ve geografía (denegación por defecto), y un alcance `national` equivale a sin restricción. Los usuarios sin alcance sí son administrables por cualquier admin con el permiso, para poder configurarlos.

**D-61 · Hallazgos de la carga real de Aguascalientes.**
- `LOCALIDAD.tipo` 2 = URBANO(A), verificado con el catálogo; esto cierra el pendiente de D-15.
- Del catálogo de colonias del INE:
  - 323 de los 2,189 pares oficiales tienen menos de 5 % de traslape geométrico (el cálculo por umbral los habría descartado);
  - 23 pares relacionan colonias con secciones que geométricamente no tocan (`catalog_pair_without_overlap`).
- En Aguascalientes no hubo geometrías inválidas, manzanas fuera de su sección ni distritos inconsistentes. El importador los detecta igual; los tests lo prueban con la BGD sintética.

**D-62 · Los códigos de colonia no son confiables a nivel nacional (corrige D-59).**
- **El error:** D-59 generalizó a partir de Aguascalientes, donde `CLASIFICAC` corresponde 1:1 al tipo de colonia. La carga nacional lo desmiente. En la Ciudad de México el código 3 aparece con 11 textos distintos en el catálogo del INE (UNIDAD HABITACIONAL 533, COLONIA 35, RESIDENCIAL 11…), y estados distintos asignan textos distintos al mismo código. Además, el importador sobrescribía la descripción con la de cada estado, y eso dejaba descripciones incorrectas.
- **Descripciones de código:** solo se aceptan mientras toda la evidencia coincide, a nivel nacional. Si un estado se contradice a sí mismo, o contradice lo que fijó otro estado, el código queda con `description_conflict = true` y sin descripción, y no se vuelve a llenar en automático. Esta regla aplica a todos los catálogos de códigos.
- **Tipo de colonia:** se guarda el **texto oficial del catálogo por colonia** en `neighborhoods.type_label`. Es la fuente correcta registro por registro, independiente del código.
- **Lección:** los mapeos de códigos se validan contra el país completo antes de darlos por buenos (se agrega a riesgos).

**D-63 · Operación de la geografía.**
- Cada corrida de importación registra tiempos por etapa (`counts.timings_s`).
- Después de reconstruir los alcances en bloque se ejecuta `ANALYZE identity.user_scope_sections` (visto en el benchmark nacional: sin estadísticas, una tesela acotada tardó 207 ms en lugar de 5.6 ms).
- `scripts/import-national.sh` carga los 32 estados desde una carpeta local.
- `scripts/benchmark_geo.py` mide la API de punta a punta.

**D-64 · Fase C aprobada.** El usuario aprobó la fase C el 2026-10-25; PR #3 fusionado a `main`.

**D-65 · Ajustes de implementación de personas y candidaturas (sobre `MODELO_DATOS.md` §3 y §4).**
- **Entidad de nacimiento:** `persons.birth_entity` guarda el código de dos letras de la CURP (`AS`…`ZS`, `NE` = nacido en el extranjero) en lugar de `birth_state_code` numérico; así se compara directo con la CURP.
- **Parámetros de reglas:** `validation_rules.default_params` (jsonb con los valores por defecto) reemplaza `params_schema`. El parámetro efectivo es `default_params || params`; un parámetro desconocido se rechaza con 400.
- **`nomination_kind = member`:** distingue los cargos que solo existen dentro de una planilla (regidurías, concejalías) de los que pueden ir solos o en planilla (sindicatura).
- **`rule_overrides`:** lleva `nomination_id` y `formula_id` opcional (la paridad es de la postulación, no de una fórmula), más `details` con el mensaje aceptado.
- **`nominations.notes`:** notas libres.
- **Vista `candidacies.nomination_sections`:** secciones que cubre cada postulación según su nivel (UNION ALL por nivel). Es la base de las reglas de lectura y edición por alcance (D-34).
- **Conflictos de reglas:** un 409 `urn:pazos:problem:rule-violation` incluye el miembro de extensión `violations` (regla, severidad, mensaje, fórmula), según RFC 9457 §3.2.

**D-66 · Personas: visibilidad, enmascarado y permisos.**
- **Visibilidad con alcance limitado (suposición):** una persona es visible si su domicilio principal está en el alcance, si integra una postulación visible para el usuario, o si aún no tiene domicilio (para poder capturarla). No se puede registrar un domicilio fuera del alcance.
- **Enmascarado:** CURP (`GOME******MASRRN07`), contactos (`******4567`, `m***@dominio`) y calle/números solo se ven completos con `people.person.read_sensitive`. La geografía del domicilio siempre se ve (D-31).
- **CURP incoherente:** forzar el registro con `accept_curp_incoherence` requiere `people.person.read_sensitive` (suposición: no se creó un permiso aparte). La persona queda marcada con `curp_coherence_overridden` y la respuesta trae las advertencias.
- **Permisos por rol** (migración 0008):
  - admin: personas completo, más candidaturas: lectura, catálogos y procesos;
  - coordinador: personas (sin borrar), lectura, captura, aprobación y excepciones de reglas;
  - capturista: personas (leer y escribir), lectura y captura de candidaturas;
  - consulta: lectura de personas y candidaturas.
- **Búsqueda:** por nombre sin acentos (índice de trigramas sobre `f_unaccent(lower(search_name))`), por CURP o por teléfono exactos vía blind index.

**D-67 · Motor de reglas: cuándo bloquea y qué se acepta.**
- **Configuración:** una fila por cargo prevalece sobre la del proceso, incluso para apagar una regla en un solo cargo. Al crear un proceso solo queda activa `unique_person_in_process`, bloqueante (D-28).
- **Ediciones de fórmulas:** se juzgan por lo que **introducen**. Se compara la evaluación antes y después del cambio, y solo bloquean las violaciones nuevas. Así una regla activada a mitad del proceso no congela la captura, pero sí se exige al enviar.
- **Excepciones:** requieren `candidacies.rule.override`, un motivo y que `override.rules` cubra todas las reglas violadas. Se registra una fila por violación aceptada, por ejemplo las dos fórmulas que comparten persona. Una violación aceptada ya no se reporta como pendiente.
- **Paridad (`gender_parity`):** solo al enviar o aprobar, y en la validación en seco (`GET /nominations/{id}/validation`). Cuenta a las propietarias de la posición 1 del cargo principal entre las postulaciones enviadas o aprobadas del mismo cargo en el proceso, más la evaluada. **Suposición:** cuenta como mujer el sexo `M`; `X` no suma a la cuota. Hay que confirmarlo según la ley de cada estado.
- **Alternancia:** compara el sexo de las propietarias en posiciones consecutivas del mismo cargo.
- **Suplente del mismo sexo:** parámetro `allow_male_owner_female_substitute`, para las legislaciones que permiten propietario hombre con suplente mujer.

**D-68 · Ciclo de vida de postulaciones y fórmulas.**
- **Fórmulas:** se agregan y editan solo mientras la postulación es borrador y la fórmula está en `aspirant`. Después solo cambian por transición o sustitución.
- **Transiciones:** `aspirant → registered` (captura), `registered → approved` (requiere `nomination.approve`) y `→ cancelled` con motivo (requiere `nomination.approve` salvo en `aspirant`).
- **Sustitución (D-29):** requiere `nomination.approve`; debe cambiar al menos a una persona. La fórmula nueva hereda la posición y el estatus de la reemplazada (suposición) y queda ligada por `replaces_formula_id`. Ambas quedan en el historial.
- **Postulación:**
  - **enviar:** exige todas las posiciones esperadas y aplica todas las reglas, incluida la paridad;
  - **aprobar:** requiere `nomination.approve`;
  - **cancelar:** cancela sus fórmulas vigentes y libera la geografía para otra postulación.
- **Creación:**
  - el cargo debe estar habilitado y no ser miembro de planilla en ese proceso;
  - el nodo debe ser del nivel del cargo y pertenecer al marco del proceso y, si es local, a su estado;
  - un municipio con `normative_system` no admite postulaciones de partido (409);
  - RP con `best_loser` espera 0 posiciones (D-21).
- **Proceso cerrado:** todo queda de solo lectura (409).
- **Alcance:** las postulaciones nacionales solo las crea y edita un usuario con alcance nacional; con alcance parcial son de solo lectura.

**D-69 · Baja de personas (ARCO) — suposición a confirmar.** `DELETE /people/{id}` hace soft-delete y fija `purge_after = hoy + 30 días`. `paz people purge`, programable con cron, anonimiza después: borra contactos, domicilios y consentimientos, y deja el nombre como `[eliminado]` y sin CURP. La fila se conserva para no romper el historial de candidaturas. No se puede dar de baja a quien integra una fórmula vigente. **El plazo de 30 días es una suposición** (`PURGE_RETENTION_DAYS`), pendiente de la política de privacidad del partido.

**D-70 · Cargos y partidos como datos.** `POST /office-types` agrega cargos sin migración; los procesos nuevos los incluyen deshabilitados. Partidos y coaliciones se administran por API. Se siembra solo PAZ (`is_own_party`); los rivales llegan después (respuesta 26).

**D-71 · Fase D aprobada.** El usuario aprobó la fase D el 2026-10-25; PR #4 fusionado a `main`.

**D-72 · Mapa base del visor: OpenFreeMap, configurable.** El usuario eligió OpenFreeMap: teselas vectoriales de OpenStreetMap, sin llave ni costo.
- Se cambia con `VITE_MAP_STYLE_URL`, que se lee al construir el panel. La CSP de producción admite el origen indicado en `PAZ_MAP_TILES_ORIGIN`.
- **Qué sale a terceros:** el navegador pide a OpenFreeMap la zona que se está viendo. No viaja ningún dato del partido; las capas electorales salen de la API con el token del usuario.
- **Worker de MapLibre:** se empaqueta con Vite (`?worker&url` y `worker.format = "es"`), porque MapLibre busca su worker junto a su propio módulo y el bundler lo mueve.

**D-73 · E2E del panel contra el stack real.** Elección del usuario.
- **Script:** `scripts/e2e.sh` corre igual en local y en CI. Levanta PostGIS y Redis desechables, aplica las migraciones, corre la semilla (`backend/tests/e2e/seed.py`), arranca la API y prueba el build de producción del panel con Playwright.
- **Semilla:** geografía sintética, proceso configurado, personas y postulaciones. Crea un usuario por escenario con secreto TOTP conocido, porque el anti-replay de TOTP y la rotación del refresh token impiden reutilizar una sesión entre tests. Los tests corren en serie.
- **CI:** el job `e2e` reemplaza al Playwright que corría dentro del job `frontend`, y este queda con Biome, `tsc`, Vitest y build.

**D-74 · Sesión del panel.**
- **Tokens:** el access token se guarda solo en memoria (`lib/auth/session.ts`) y el refresh token sigue en cookie httpOnly (D-48). Al recargar, la guarda del layout autenticado renueva con la cookie.
- **401:** el `fetch` del cliente generado renueva una sola vez, con un único refresh en vuelo compartido por las peticiones concurrentes (dos refresh en paralelo parecerían reuso y cerrarían la sesión), y repite la petición. Si la renovación falla, manda al login conservando la ruta.
- **Redirección tras el login:** solo acepta rutas internas, para no abrir redirecciones a otros sitios.
- **Enrolamiento:** los tokens con alcance `mfa_enrollment` solo llegan a `/enroll-mfa`.

**D-75 · Convenciones del panel.**
- **Formularios:** TanStack Form (`createFormHook`) validado con los esquemas Zod generados del OpenAPI. Los campos vacíos se convierten en `null` antes de validar y enviar, y los mensajes salen en español (`z.locales.es`).
- **Selects nativos** para catálogos cortos: son accesibles y permiten buscar tecleando.
- **Autocompletado asíncrono** (Radix Popover + cmdk) para personas y geografía: se abre con la primera tecla, Enter elige y Supr limpia.
- **Tablas:** TanStack Table v9 con orden y paginación del lado del servidor. Para que "Anterior" funcione con cursores que solo avanzan, se guarda una pila de cursores.
- **Atajos:** `Ctrl+K`, `/`, `N`, `↑ ↓ Enter` y `Ctrl+Enter`. Las teclas sueltas se ignoran mientras se escribe en un campo.
- **Excepciones a reglas:** un 409 `rule-violation` abre un diálogo para quien tiene `candidacies.rule.override`. Pide el motivo y reintenta con `override`.
- **Lo que se muestra:** el panel oculta lo que el usuario no puede hacer; el backend es quien decide.
- **Tema:** solo tema claro por ahora.

**D-76 · Edición de cargos.** `PATCH /office-types/{id}` cambia nombre, posiciones por defecto, suplencia y orden. El código, los niveles, el principio y el tipo de postulación quedan fijos al crearse, porque las postulaciones dependen de ellos.

**D-77 · Fase E aprobada; MVP completo.** El usuario aprobó la fase E el 2026-10-25; PR #5 fusionado a `main`. Con ella quedan entregadas las 5 fases del plan (D-42).

**D-78 · Identidad visual del panel.** Colores de identidad: morado PAZ `#682575` y blanco; tipografía Montserrat. Lineamientos tomados de partidopaz.mx: títulos gruesos, botones tipo píldora, tarjetas blancas con sombra morada suave y paneles con degradado morado (menú lateral, inicio de sesión y portada).
- **Paleta:** los tokens de `src/index.css` derivan del morado (OKLCH, tono 320.8). Los grises llevan un matiz morado. `--brand`, `--brand-strong` y `--brand-soft` quedan disponibles como utilidades (`bg-brand-soft`, `shadow-brand`, `bg-brand-gradient`).
- **Montserrat autoalojada** con `@fontsource-variable/montserrat`: son los mismos archivos de Google Fonts, empaquetados con el panel. No se carga desde el CDN de Google por tres razones: la CSP de producción solo permite fuentes del propio origen; no se envía la IP de cada usuario a un tercero (LFPDPPP); y no hay petición adicional a otro dominio. El navegador descarga solo el subconjunto latino (~38 kB, una fuente variable con todos los pesos).
- **Logotipo:** `components/brand/logo.tsx` genera `PazosLogo` (logotipo completo) y `PazosMark` (óvalo con la paloma) desde el arte oficial en `docs/brand/` (`pazos-logo-white.svg` y `pazos-logo-ovalo-white.svg`), con `currentColor`. El favicon es el óvalo sobre morado.
- Solo tema claro (suposición 1 de la fase E). Los colores de las capas del mapa no cambian, porque cada nivel necesita un color distinto.

---

## Suposiciones vigentes

- El ID de origen de colonia en la BGD es estable entre cortes (D-10/D-58: único y consistente con el catálogo dentro del corte; la estabilidad entre cortes queda por verificar).
- El umbral por defecto colonia ↔ sección es 5 % del área de la colonia o 500 m² (D-09).
- No se precargan reglas electorales por estado (regidurías, sindicatura, régimen municipal, paridad); todo es configuración (D-24 a D-28).
- La primera minoría del Senado se infiere de la posición 1 de la lista estatal; el cálculo de resultados queda fuera del MVP.
- Personas visibles con alcance limitado: domicilio en el alcance, postulación visible o sin domicilio aún (D-66).
- Forzar una CURP incoherente usa el permiso `people.person.read_sensitive` (D-66).
- Paridad: cuenta como mujer el sexo `M`; `X` no suma a la cuota (D-67).
- Una fórmula sustituta hereda el estatus de la reemplazada (D-68).
- Retención de 30 días antes de anonimizar a una persona dada de baja (D-69).

## Riesgos abiertos

- ~~Disponibilidad de PG18 + PostGIS en Postgres administrado (D-05).~~ **Resuelto el 2026-10-24:** DigitalOcean administrado ofrece PostGIS en PostgreSQL 18 (Standard Edition, según su lista oficial de extensiones) y AWS RDS ofrece PostgreSQL 18.4 con PostGIS 3.6.3. Se mantiene PG18 sin fallback.
- Cadena de hashes de la bitácora con alta concurrencia: requiere serializar la escritura del eslabón (secuencia o lock ligero) y medir su costo en carga.
