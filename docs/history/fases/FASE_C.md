# Cierre de fase C — Geografía y alcance geográfico

**Fecha:** 2026-10-25 · **Rama:** `feat/phase-c-geography` · **Estado:** aprobada el 2026-10-25 · PR [#3](https://github.com/edgardarbeni/paz-crm/pull/3) (D-64).

## Criterios de aceptación (PLAN_FASES.md)

| Criterio | Resultado | Evidencia |
|---|---|---|
| La importación de Aguascalientes es idempotente: la segunda corrida da 0 insertados y 0 actualizados, con los mismos IDs | ✅ | Carga real de Aguascalientes: la segunda corrida da 0/0 en las 9 tablas y el hash de IDs de sección es idéntico; test `test_reimport_is_idempotent_and_keeps_ids` |
| El dry-run no escribe nada | ✅ | `test_dry_run_writes_nothing_but_the_run`: solo queda la corrida con su reporte |
| Conteos contra el origen | ✅ | Aguascalientes: 1 / 11 / 3 / 18 / 736 / 1,769 / 1,729 / 25,482 / 1,265, idénticos a la fuente |
| Validaciones de `DISENO_BD` §5 | ✅ | Geometrías inválidas reparadas, manzanas fuera de su sección, distritos de manzana distintos a los de su sección y padres inexistentes, como incidencias por registro |
| Tests negativos de alcance | ✅ | `test_geography_api.py`: sin alcance no ve nada; con alcance de sección no ve otras secciones (listados, detalle, búsqueda, `locate` y teselas); no otorga alcance fuera del suyo; la administración de usuarios queda limitada por alcance |
| **Benchmark nacional**: punto-en-polígono < 50 ms p95, lecturas < 200 ms p95 | ✅ | `locate` 4.8 ms y lecturas ≤ 58 ms en el p95, con usuario sin restricción y con usuario acotado (ver abajo) |

## Benchmark nacional

**Carga.** Los 32 estados se importaron desde `paz-maps/` con los catálogos del INE en unos 17 min, sin errores (`scripts/import-national.sh`).

| Elemento | Cargado | Análisis original |
|---|---|---|
| Municipios / DF / DL | 2,477 / 300 / 679 | 2,477 / 300 / 679 ✅ |
| Secciones | 73,268 | 73,268 ✅ |
| Manzanas | 2,502,184 | 2,502,184 ✅ |
| Circunscripciones | 5 | 1–5 ✅ |
| Localidades | 215,242 | puntos + polígonos |
| Colonias | 123,434 | 116,661 + colonias puntuales |
| Pares colonia–sección | 213,244 | catálogo INE + cálculo |

La base completa ocupa 2.5 GB (sin capas no electorales, D-13).

**Lecturas.** Medidas de punta a punta por la API (`https://localhost`: Caddy, JWT, sesión y alcance) con `scripts/benchmark_geo.py`, sobre 500 coordenadas al azar en secciones de todo el país:

| Endpoint | Usuario | p50 | p95 | Objetivo |
|---|---|---|---|---|
| `locate` (punto-en-polígono) | sin restricción | 3.7 ms | **4.8 ms** | < 50 ms ✅ |
| `locate` | acotado (CDMX, 5,589 secciones) | 4.7 ms | 6.5 ms | < 50 ms ✅ |
| Listado de 50 secciones | sin restricción | 23.2 ms | 27.3 ms | < 200 ms ✅ |
| Listado de 50 secciones | acotado | 13.3 ms | 15.7 ms | < 200 ms ✅ |
| Búsqueda por clave | sin restricción | 5.3 ms | 6.7 ms | < 200 ms ✅ |
| Búsqueda por nombre | sin restricción / acotado | 18.5 / 43.1 ms | 21.1 / 58.3 ms | < 200 ms ✅ |
| Tesela de manzanas z15 | sin caché / acotado | 5.9 / 4.9 ms | — / 5.6 ms | — |
| Tesela de secciones z11 | acotado | 46.9 ms | 48.9 ms | — |

En la primera medición, la tesela de manzanas del usuario acotado dio 207 ms. La causa: `user_scope_sections` acababa de recibir 5,589 filas sin estadísticas, y el planificador eligió un mal plan. Con la tabla analizada baja a 5.6 ms. Se agregó `ANALYZE` tras las reconstrucciones masivas (activación de marco) y queda como riesgo R-7.

**Importación.** Cada corrida reporta tiempos por etapa (`counts.timings_s`). Veracruz, por ejemplo, tarda unos 11 s en la importación misma; los 288 s del script incluían la descarga de catálogos y la primera inserción.

## Entregables

| Área | Entregado |
|---|---|
| Modelos y migraciones | `0005`: 21 tablas de `geography`, con FKs compuestas por marco, manzanas particionadas por marco, índices GiST y de trigramas. `0006`: `user_scopes`, `user_scope_sections` y 3 permisos |
| Importador | `paz geo download` (índice público del INE, manifiesto con hashes) y `paz geo import` (carpeta o 7z, pyogrio, validación por registro, `COPY` y upsert por llave natural, desactivación segura, dry-run, diario de corrida independiente) |
| Datos derivados | Geometría de circunscripciones, secciones subdivididas, relación colonia–sección del catálogo INE más el cálculo espacial, descripciones de códigos con consistencia nacional, tipo de colonia por registro |
| Marcos | `paz geo activate`: activa un marco y remapea los alcances por llave natural |
| API | `/api/v1/geography`: niveles con filtros y cursor, detalle con GeoJSON y ancestros, búsqueda por clave o nombre, `locate`, teselas MVT con caché, corridas e incidencias, marcos |
| Alcance (D-34) | `PUT/GET /users/{id}/scopes`, alcance en `/auth/me`, filtro SQL en todas las consultas geográficas y en la administración de usuarios |
| Scripts | `scripts/seed-dev-geo.sh` (Aguascalientes) y `scripts/import-national.sh` (32 estados) |
| Pruebas | BGD sintética generada en cada test (sin red ni datos versionados), con casos de borde |
| Documentación | D-57 a D-63, `MODELO_DATOS.md` actualizado, carpeta `geography/` en Bruno, README |

## Hallazgos de datos

1. **`CLASIFICAC` no es un código confiable a nivel nacional (D-62).** En la Ciudad de México el código 3 aparece con 11 tipos de colonia distintos. Se corrigió:
   - las descripciones de código solo se aceptan si toda la evidencia nacional coincide;
   - el tipo oficial de cada colonia se guarda por registro (`type_label`).

   Lo descubrió la carga nacional. En Aguascalientes el mapeo era perfecto, y D-59 lo había generalizado por error.
2. **El catálogo de colonias del INE relaciona muchas colonias con secciones que no tocan.** Algunos ejemplos: 8,491 pares en Chiapas, 7,933 en Guanajuato y 5,492 en Coahuila. Se conservan, porque son la relación oficial (D-57), y se reportan como advertencias para revisión.
3. **Geometrías:** el estado 21 (Puebla) trae polígonos de colonia con el sentido de anillos invertido; GDAL los corrige al leer. En los 32 estados hay manzanas dibujadas fuera de su sección (por ejemplo, 150 en Chiapas), reportadas como advertencias.
4. **`LOCALIDAD.tipo` 2 = URBANO(A)**, verificado con el catálogo.

## Errores encontrados y corregidos durante la fase

1. **Descripciones de código incoherentes entre estados** (detalle en Hallazgos 1). Se detuvo la primera carga nacional, se corrigió el esquema y la lógica, y se repitió la carga.
2. **asyncpg:** no infiere el tipo de un parámetro en la lista del `SELECT`, así que se hace cast explícito a `uuid`. Además, una tabla particionada no expone `xmax`; se usa `RETURNING old.id IS NULL` de PostgreSQL 18.
3. **Test de deriva:** detectaba las tablas que crean los propios tests y las particiones creadas en tiempo de ejecución. Ahora corre en un proceso aparte y `env.py` ignora las particiones.
4. **CLI:** los errores de validación se mostraban como traceback; ahora son un mensaje claro.

## Suposiciones

1. **Llave de colonia:** `(estado, ID BGD)`. La estabilidad del ID entre cortes sigue sin verificarse, porque solo hay un corte (D-58).
2. **Colonias puntuales:** sus llaves llevan prefijo `P` para no chocar con las de polígono (D-58).
3. **Umbral del cálculo colonia–sección:** 5 % del área o 500 m² (D-09). Solo aplica a colonias que el catálogo no cubre.
4. **Usuarios sin alcance:** no ven geografía; cualquier admin con el permiso puede administrarlos (D-60).
5. **Manzanas fuera de su sección o con distritos distintos:** solo generan advertencias; manda la sección (D-20).

## Deuda técnica

| # | Deuda | Cuándo atenderla |
|---|---|---|
| DT-17 | Las teselas de usuarios acotados no se cachean (se calculan siempre, 5–50 ms); la caché por usuario necesita invalidarse al cambiar el alcance | Si el visor de la fase E lo requiere |
| DT-18 | El catálogo de colonias se lee del `.xls` con `xlrd`; si el INE deja de publicar `.xls`, habrá que leer el `.mdb` | Cuando cambie el formato |
| DT-19 | Las incidencias `catalog_pair_without_overlap` son muchas (miles por estado) y se guardan una por una | Resumir por colonia si estorban en el visor |
| DT-20 | Las importaciones se lanzan solo por CLI; el panel solo las consulta (D-42) | Fase posterior (worker) |
| DT-21 | ~~Faltan los domicilios de personas en el remapeo de marcos~~ | Cerrada en la fase D |

## Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-7 | Planes malos tras cargas masivas en `user_scope_sections` (visto en el benchmark: 207 ms en lugar de 5.6 ms) | `ANALYZE` tras reconstrucciones masivas; autovacuum para cambios individuales; vigilar en métricas |
| R-8 | Generalizar reglas de datos desde un solo estado (le pasó a D-59) | Validar todo mapeo de códigos contra la carga nacional antes de darlo por bueno |
| R-2 | (Fase A) contención en la cadena de auditoría | Las importaciones escriben una sola entrada por corrida; sin cambios |
