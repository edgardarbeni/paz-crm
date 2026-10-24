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

---

## Suposiciones vigentes

- El ID de origen de colonia en la BGD es estable entre cortes (D-10, por verificar).
- El umbral por defecto colonia ↔ sección es 5 % del área de la colonia o 500 m² (D-09).
- No se precargan reglas electorales por estado (regidurías, sindicatura, régimen municipal, paridad); todo es configuración (D-24 a D-28).
- La primera minoría del Senado se infiere de la posición 1 de la lista estatal; el cálculo de resultados queda fuera del MVP.

## Riesgos abiertos

- Disponibilidad de PG18 + PostGIS en Postgres administrado (D-05).
- Cadena de hashes de la bitácora con alta concurrencia: requiere serializar la escritura del eslabón (secuencia o lock ligero) y medir su costo en carga.
