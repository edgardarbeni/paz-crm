# Módulo: Geografía electoral

Código: `backend/app/modules/geography` · esquema `geography` · migraciones `0005` y `0010` · API `/api/v1/geography`.
Modelo completo: [`reference/data-model.md` §1](../reference/data-model.md). Referencia de las capas del INE: [`reference/DISENO_BD_GEOESPACIAL.md`](../reference/DISENO_BD_GEOESPACIAL.md).

## Propósito y usuarios

Es la base territorial de todo el sistema: el modelo electoral del país (circunscripción, estado, distrito federal, distrito local, municipio, sección) y la geografía tradicional ligada a la sección (manzana, colonia, localidad), cargados de la BGD y los catálogos del INE.

| Quién | Para qué |
|---|---|
| Todos los roles con `geography.node.read` | Explorar y buscar nodos, ubicar una coordenada y ver el mapa |
| Admin | Revisar corridas de importación e incidencias (`geography.import.read`) |
| Operación (CLI, rol dueño de la BD) | Descargar, importar y activar marcos (`paz geo …`) |
| Otros módulos | Resolver el alcance geográfico, ubicar postulaciones y domicilios |

Pantallas del panel: Explorador (`/geography`), detalle de nodo (`/geography/$level/$nodeId`), Mapa (`/geography/map`), Ubicar coordenada (`/geography/locate`) e Importaciones (`/geography/imports`).

**Detalle de nodo ([D-81](../adr/D-81-contiene-en-detalle-de-nodo.md)).** El mapa resalta el nodo; a un lado, «Pertenece a» (ancestros) y «Contiene».
- «Contiene» tiene un grupo abatible por nivel hijo con su conteo dentro del alcance (p. ej. Baja California: 7 municipios, 9 distritos federales, 17 distritos locales y 2,254 secciones). Los grupos vacíos no se muestran.
- Cada grupo lista ahí mismo los hijos, de 50 en 50 («Mostrar más»), con filtro por número o nombre cuando son más de 12, y un enlace al Explorador filtrado.
- El primer grupo se abre solo si tiene 30 elementos o menos; uno largo ocultaría a los demás. El encabezado de un grupo abierto queda fijo al desplazarse, para poder cerrarlo.
- Abrir un grupo dibuja su capa en el mapa sin mover la cámara. Al pasar el cursor (o el foco) por un hijo, se resalta en el mapa si su capa ya tiene teselas a ese zoom (secciones desde z9, colonias desde z12; las localidades no tienen capa).
- En pantallas anchas la barra lateral mide lo mismo que el mapa y «Contiene» se desplaza por dentro; en móvil va debajo del mapa.

## Dependencias

- `app.core`: `db.base` (`ImportedMixin`), `audit` (`record_audit`), `pagination`, `errors`.
- `identity`: `CurrentUser`, `permission(Perm.…)` y `GeoScope` (`identity/services/scopes.py`). Al activar un marco llama a `rebuild_all` para reconstruir `user_scope_sections`.
- `people`: la activación de marco remapea `people.person_addresses` (única escritura hacia otro módulo).
- PostgreSQL 18 + PostGIS 3.5+ ([D-05](../adr/D-05-postgresql-18-postgis-3-5.md)), extensiones `pg_trgm` y `unaccent` (`public.f_unaccent`), Redis para caché de teselas.
- Importador: `pyogrio`, `py7zr`, `xlrd` (catálogo de colonias en `.xls`).

## Entidades y relaciones

**Marco versionado ([D-01](../adr/D-01-marco-geografico.md), [D-02](../adr/D-02-recarga.md)).** Toda entidad pertenece a un `geographic_frameworks` (p. ej. "INE dic-2025"). Pueden coexistir varios, pero solo uno está activo (`UNIQUE` parcial sobre `is_active`). Un marco nuevo solo se crea cuando hay redistritación; recargar un marco existente es un upsert por llave natural que conserva los IDs.

**Jerarquía electoral ([D-06](../adr/D-06-modelo-conceptual.md)).**
- `electoral_regions` (circunscripción) > `states` > (`federal_districts` | `local_districts` | `municipalities`) > `sections`.
- La **sección** es la unidad atómica: pertenece a exactamente un municipio, un DL y un DF. DF, DL y municipio son agrupaciones independientes que se traslapan; ninguna está anidada en otra.
- Circunscripción: la asignación estado → circunscripción viene de `ENTIDAD.circunscri`; su geometría se calcula como `ST_Union` de los estados ([D-07](../adr/D-07-circunscripcion.md)).
- No se modelan circunscripciones plurinominales locales ([D-08](../adr/D-08-diputaciones-locales-rp.md)).
- `section_parts`: secciones subdivididas (`ST_Subdivide`) para el punto-en-polígono.
- Geometrías generalizadas para teselas ([D-80](../adr/D-80-teselas-geometrias-generalizadas.md)): `geom_low` (z ≤ 6) y `geom_mid` (z 7–9) en estados, distritos federales, distritos locales y municipios; `geom_mid` en secciones. Son copias de `geom` simplificadas con `ST_SimplifyPreserveTopology` a 4 unidades de tesela del zoom máximo de su banda (≤ ½ píxel). Nullable: sin ellas la tesela usa `geom`.

**Geografía tradicional.**
| Entidad | Relación con la sección | Notas |
|---|---|---|
| `blocks` (manzana) | N:1 por la clave de la BGD | Sus distritos se obtienen siempre por la sección; no se guardan. Particionada por `framework_id` ([D-14](../adr/D-14-particionado.md)) |
| `neighborhoods` (colonia) | N:M en `neighborhood_sections` | Fuente principal: catálogo del INE (`source = 'ine_catalog'`); el cálculo espacial agrega pares para colonias no cubiertas (`computed`, umbral configurable) y calcula % y área de traslape ([D-57](../adr/D-57-relacion-colonia-seccion-desde-catalogo-ine.md)). Llave `(estado, ID BGD)`; las puntuales llevan prefijo `P` ([D-58](../adr/D-58-verificaciones-llave-colonia-fuentes-importador.md)). Tipo oficial por registro en `type_label` ([D-62](../adr/D-62-codigos-colonia-no-son-confiables-nivel.md)) |
| `localities` + `locality_sections` | Polígono de localidad + un punto por par localidad-sección | [D-11](../adr/D-11-localidades.md) |

**Catálogos de códigos** (`section_types`, `federal_district_types`, `block_statuses`, `locality_types`, `locality_head_types`, `neighborhood_types`): `code`, `description`, `description_source`. Las descripciones salen de los catálogos oficiales del INE; sin evidencia quedan `NULL` ([D-15](../adr/D-15-catalogos-codigos.md)). Una descripción solo se acepta si toda la evidencia nacional coincide; si hay contradicción queda `description_conflict = true` y no se vuelve a llenar ([D-62](../adr/D-62-codigos-colonia-no-son-confiables-nivel.md)).

**Importaciones.** `import_runs` (archivo, hash SHA-256, conteos por tabla en `counts`, tiempos por etapa en `counts.timings_s`, `dry_run`, `status`) e `import_issues` (error o advertencia por registro) ([D-60](../adr/D-60-ajustes-implementacion-geografia.md), [D-63](../adr/D-63-operacion-geografia.md)).

**Convenciones propias ([D-03](../adr/D-03-pk-hibrida.md), [D-04](../adr/D-04-geografia-solo-lectura.md), [D-41](../adr/D-41-modelo-datos-aprobado.md) punto 6).** UUIDv7 en entidades referenciadas y `bigint` en tablas masivas no referenciadas; sin `deleted_at` (`is_active` + `import_run_id`); `framework_id` en todas las tablas con FKs compuestas `(framework_id, parent_id)`. Geometrías en SRID 4326 con índices GiST; registros sin geometría se conservan con `geom NULL` ([D-12](../adr/D-12-registros-sin-geometria.md)).

## Reglas de negocio

- **Solo lectura:** la geografía únicamente cambia por importación; no hay endpoints de escritura ([D-04](../adr/D-04-geografia-solo-lectura.md)).
- **Importador idempotente ([D-18](../adr/D-18-importador.md), [D-58](../adr/D-58-verificaciones-llave-colonia-fuentes-importador.md), [D-60](../adr/D-60-ajustes-implementacion-geografia.md)):**
  - Fuente: carpeta de shapefiles de la BGD o el `.7z` oficial; catálogos INE (txt/xlsx/xls) descargados con `paz geo download` ([D-16](../adr/D-16-fuente-datos-primer-marco.md)).
  - Normaliza encoding, `SIN NOMBRE` → `NULL`, reproyecta a EPSG:4326, valida por registro, carga con `COPY` y hace upsert por llave natural.
  - `--dry-run` no escribe nada salvo la corrida y su reporte.
  - Lo que desaparece del origen queda `is_active = false`, pero solo en capas que cargaron sin errores (`deactivation_skipped` en otro caso).
  - Al final de cada estado calcula las geometrías generalizadas (`derived.generalized_geometries` en el reporte); si no cambiaron no las reescribe. `paz geo generalize [--framework]` las calcula para datos ya cargados.
  - Validaciones por registro: geometrías inválidas reparadas, manzanas fuera de su sección, distritos de manzana distintos a los de su sección, padres inexistentes, pares del catálogo sin intersección (`catalog_pair_without_overlap`). Son advertencias; manda la sección.
- **Activación de marco** (`paz geo activate --framework NOMBRE`, [D-41](../adr/D-41-modelo-datos-aprobado.md) punto 7): remapea alcances de usuario y domicilios por llave natural; lo que no tiene equivalente se elimina (alcances) o se limpia (nodos del domicilio) y se reporta; reconstruye `user_scope_sections` y ejecuta `ANALYZE` ([D-63](../adr/D-63-operacion-geografia.md)).
- **Búsqueda (`GET /geography/search`, [D-19](../adr/D-19-api-geografica.md), [D-79](../adr/D-79-busqueda-geografica-nombre-estado.md)):** clave INE flexible (`09-0123`, `9 123`, `090123`), número + estado en cualquier orden con palabras de nivel opcionales, nombre + estado, o solo estado (con `level`, devuelve lo que contiene); `state_id` opcional. El estado se reconoce por nombre o inicio de palabra, sin catálogo de abreviaturas. Las respuestas incluyen `state_name` y `municipality_name`.
- **Consulta jerárquica:** qué contiene un nodo y cuántos hay por nivel con `GET /geography/{level}/{node_id}/children` (dentro del alcance; 403 fuera de él); los hijos con `GET /geography/{level}` filtrando por el padre (`state_id`, `municipality_id`…) y paginación por cursor; ancestros en el detalle (`GET /geography/{level}/{node_id}`, la sección incluye `ancestors`) y en `locate`.
- **Pendiente de definir:** estabilidad del ID de colonia entre cortes (solo hay un corte, [D-58](../adr/D-58-verificaciones-llave-colonia-fuentes-importador.md)); significado de `C` y `*` en `MANZANA.status` ([D-15](../adr/D-15-catalogos-codigos.md)).

## Permisos y alcance

| Permiso | Uso | Roles semilla (migración 0006) |
|---|---|---|
| `geography.node.read` | Niveles, detalle, búsqueda, `locate`, teselas, marcos | admin, coordinator, capturist, viewer |
| `geography.import.read` | Corridas e incidencias de importación | admin |

Importar y activar marcos no tiene permiso de API: es operación por CLI con el rol dueño ([D-42](../adr/D-42-plan-fases-aprobado.md), deuda DT-20).

**Alcance ([D-34](../adr/D-34-alcance-geografico.md), [D-60](../adr/D-60-ajustes-implementacion-geografia.md)):** un nodo es visible si toca al menos una sección del alcance del usuario (`LevelDef.visible(geo)`, `EXISTS` contra `identity.user_scope_sections`). Aplica a listados, detalle, búsqueda, `locate` y teselas. Sin alcance no se ve nada; superadmin y alcance `national` no tienen restricción.

## Datos sensibles

No guarda datos personales: la BGD y los catálogos del INE son información pública. No hay campos cifrados ni auditoría de lectura. El mapa base del visor (OpenFreeMap) solo recibe la zona que se mira; las capas electorales salen de la API con el token del usuario ([D-72](../adr/D-72-mapa-base-visor-openfreemap-configurable.md)).

## Volumen y rendimiento

Carga nacional real (BGD dic-2025, 32 estados, ~17 min, `scripts/import-national.sh`; [FASE_C](../history/fases/FASE_C.md)):

| Elemento | Registros |
|---|---|
| Municipios / DF / DL | 2,477 / 300 / 679 |
| Secciones | 73,268 |
| Manzanas | 2,502,184 |
| Localidades | 215,242 |
| Colonias / pares colonia–sección | 123,434 / 213,244 |
| Tamaño de la base | 2.5 GB |

Medido de punta a punta por la API con `scripts/benchmark_geo.py` (500 coordenadas al azar):

| Consulta crítica | p95 | Objetivo |
|---|---|---|
| `locate` sin restricción / acotado | 4.8 / 6.5 ms | < 50 ms |
| Listado de 50 secciones sin restricción / acotado | 27.3 / 15.7 ms | < 200 ms |
| Búsqueda por clave | 6.7 ms | < 200 ms |
| Búsqueda por nombre sin restricción / acotado | 21.1 / 58.3 ms | < 200 ms |
| Búsqueda D-79 (todos los formatos, local) | 5–24 ms | < 200 ms |
| Tesela de secciones z11 acotada | 48.9 ms | — |

- Teselas MVT: `ST_AsMVT` sobre la geometría generalizada de la banda de zoom ([D-80](../adr/D-80-teselas-geometrias-generalizadas.md)) y sobre `geom` desde z10; caché en Redis (`PAZ_GEO_TILE_CACHE_SECONDS`, 3600 s, llaves `tile:v2:…`) solo para usuarios sin restricción (las acotadas se calculan siempre, DT-17).
- Teselas medidas con la carga nacional (PostGIS directo, sin caché, sobre CDMX), antes y después de D-80 (2026-10-28):

  | Tesela | Antes | Después | Acotada a CDMX (después) |
  |---|---|---|---|
  | Municipios z6 | 343–458 ms · 900 KB | 24–58 ms · 188 KB | 5–11 ms |
  | Distritos locales z6 | 190–230 ms · 360 KB | 13–18 ms · 48 KB | 5–9 ms |
  | Distritos federales z6 | 158–189 ms · 269 KB | 10–13 ms · 33 KB | 5–14 ms |
  | Estados z4 | 72–152 ms · 57 KB | 9–54 ms · 17 KB | 5–49 ms |
  | Secciones z9 | 66–130 ms · 790 KB | 43–114 ms · 504 KB | 31–36 ms |
  | Secciones z ≥ 11, colonias, manzanas | 1–35 ms | sin cambio (usan `geom`) | — |

  - Una pantalla completa en z6 (72 teselas de estados, distritos federales y municipios) pasó de 0.55–0.72 s y 3.1 MB a 85–243 ms y 534 KB. Un acierto en Redis tarda 0.07 ms.
  - Contenido: en 1,863 teselas de z5 a z9 los nodos visibles son idénticos a los de `geom`. Solo 19 de 107 mil rasgos difieren, todos en el margen de 64 unidades fuera del área visible.
  - Visor (Chromium sin interfaz, gráficos por software, capas por defecto): el desplazamiento pasó de 30–31 a 52–55 cuadros por segundo. No hay fuga de memoria: el heap queda plano en ~41 MB tras 180 saltos. Las capas ocultas no descargan teselas.
  - En z5–z6 el trazo se ve un poco más delgado: la geometría original zigzagueaba dentro del mismo píxel y engrosaba la línea. Formas y posiciones coinciden.
  - Generar las columnas para todo el país toma 47 s (80,244 geometrías). En secciones z9 el peso viene de la cantidad de polígonos; subir el zoom mínimo de secciones queda como decisión de producto aparte.
- Riesgo R-7: planes malos en `user_scope_sections` tras cargas masivas sin estadísticas (207 ms en lugar de 5.6 ms); mitigado con `ANALYZE`.
- Datos de desarrollo y CI: Aguascalientes, 736 secciones y ~25 mil manzanas (`scripts/seed-dev-geo.sh`, [D-20](../adr/D-20-datos-desarrollo-ci.md)); los tests usan una BGD sintética.

## Integraciones y eventos

| Hacia | Qué |
|---|---|
| `identity` | `sections` es la base de `user_scope_sections`; los alcances apuntan a nodos geográficos y se validan contra el marco activo. La activación remapea alcances y llama a `rebuild_all` |
| `candidacies` | Las postulaciones apuntan a un nodo (municipio, DL, DF, estado, circunscripción); la vista `candidacies.nomination_sections` deriva sus secciones |
| `people` | `person_addresses` guarda estado, municipio, sección, localidad y colonia; se remapean al activar un marco |
| Bitácora | Una entrada `geo_import` por corrida (no por fila, [D-36](../adr/D-36-auditoria-importaciones.md)) y una `framework_activated` con el reporte de remapeo; las tablas geográficas tienen `__audit__ = False` |
| Panel | Selectores de geografía (`searchGeoItems`, `geoNodeLabel`) en domicilios, alcances, postulaciones y procesos |

No emite eventos asíncronos; todo ocurre dentro de la transacción de la importación o activación.

## Criterios de aceptación

| Escenario | Estado / evidencia |
|---|---|
| Dada una coordenada, devolver sección, municipio, DL, DF, estado y circunscripción en < 50 ms p95 con la carga nacional | ✅ 4.8 ms (`benchmark_geo.py`, `test_locate_point`) |
| Lecturas < 200 ms p95 con ≥ 70,000 secciones y 2.5 M de manzanas | ✅ ≤ 58 ms |
| Reimportar el mismo estado da 0 insertados / 0 actualizados y los mismos IDs | ✅ `test_reimport_is_idempotent_and_keeps_ids` |
| Un cambio en el origen actualiza y desactiva sin cambiar IDs | ✅ `test_reload_with_changes_updates_and_deactivates` |
| `--dry-run` no escribe nada salvo la corrida | ✅ `test_dry_run_writes_nothing_but_the_run` |
| Conteos iguales a la fuente y reporte de errores por registro | ✅ `test_full_import_counts_and_issues`; carga real de Aguascalientes y nacional |
| Acepta carpeta o `.7z`; capa obligatoria ausente falla limpio; capas opcionales pueden faltar | ✅ `test_7z_source`, `test_missing_required_layer_fails_cleanly`, `test_optional_layers_may_be_missing` |
| Descripciones de código contradictorias quedan vacías para siempre | ✅ `test_conflicting_code_descriptions_are_cleared_for_good` |
| Búsqueda por clave, número + estado, nombre + estado y solo estado | ✅ `test_search_by_key_and_name`, `test_search_by_number_or_name_with_state`, `test_explorer_search_by_number_or_state` |
| Teselas MVT por capa y zoom | ✅ `test_vector_tiles` |
| El detalle de un nodo lista lo que contiene, con conteos por nivel limitados al alcance, sin ir al Explorador | ✅ `test_node_children_counts`, `test_node_children_only_count_the_scope`, e2e `geography.spec.ts` |
| Teselas de zoom bajo con geometría generalizada: municipios z6 ≤ 200 KB y ≤ 50 ms con la carga nacional, mismo contenido para usuarios acotados ([D-80](../adr/D-80-teselas-geometrias-generalizadas.md)) | ✅ 188 KB, 24–33 ms con buffers calientes (58 ms en frío); `test_tiles_use_generalized_geometry_by_zoom`, `test_generalize_fills_low_zoom_columns_and_skips_current_rows`, `test_reimport_is_idempotent_and_keeps_ids` |
| Un usuario sin alcance no ve nada; uno con alcance de sección no ve otras secciones en listados, detalle, búsqueda, `locate` ni teselas | ✅ `test_user_without_scope_sees_nothing`, `test_section_scope_limits_every_query`, `test_scoped_tiles_only_contain_the_scope` |
| No se otorga alcance fuera del propio | ✅ `test_scope_assignment_cannot_exceed_own_scope` |
| Activar un marco remapea alcances y domicilios por llave natural | ✅ `test_activation_remaps_scopes`, `test_activation_remaps_person_addresses` |
| Modelos y migraciones no divergen | ✅ `test_models_and_migrations_do_not_drift` |
| La estabilidad del ID de colonia entre cortes se verifica con dos cortes | ⏳ Pendiente: solo hay un corte |

## Fuera de alcance

- Capas no electorales: vialidades, carreteras, POI, hidrografía, litoral, módulos/vocalías INE y números exteriores; irán a un módulo futuro `cartography` ([D-13](../adr/D-13-capas-no-electorales-fuera-mvp.md)).
- Importación desde KML; el importador tiene una interfaz de fuente para agregar formatos ([D-17](../adr/D-17-kml-fuera-mvp.md)).
- Edición de geografía desde el panel o la API ([D-04](../adr/D-04-geografia-solo-lectura.md)).
- Lanzar importaciones desde el panel (solo se consultan; DT-20).
- Circunscripciones plurinominales locales ([D-08](../adr/D-08-diputaciones-locales-rp.md)).
- Históricos electorales y resultados por sección (módulos futuros del brief).
