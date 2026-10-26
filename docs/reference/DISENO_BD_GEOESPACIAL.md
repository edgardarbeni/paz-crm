# Diseño de base de datos geoespacial (PostgreSQL + PostGIS)

**Fuente analizada:** cartografía electoral (BGD del INE) de los **32 estados**, en las carpetas `01 AGUASCALIENTES/` … `32 ZACATECAS/`. Son 1,596 shapefiles y ocupan 8.7 GB.
**Objetivo:** cargar todo en una sola base PostgreSQL/PostGIS con un modelo nacional, limpio y relacionado, que se pueda recargar estado por estado.

> Versión 2. Los hallazgos de la versión 1 venían solo de Baja California. Aquí se verificaron en los 32 estados, y donde había diferencias se corrigió el diseño.

---

## 1. Hallazgos que condicionan el diseño

### 1.1 Inventario de capas
Hay **54 capas distintas**. **40 aparecen en los 32 estados** y las demás varían:

| Capa | Estados | Observación |
|---|---|---|
| ADOQUIN | 26 | falta en 12, 22, 23, 27, 29, 31 |
| AEROPUERTO | 31 | falta en 29 |
| EDIFICIO | 31 | falta en 08 |
| TERRACERIA | 31 | falta en 15 |
| VEREDA | 31 | falta en 01 |
| FERROCARRIL | 30 | falta en 03, 12 |
| VOCAL_EJECUTIVO_ESTATAL, VOCAL_ESTATAL_DEL_RFE | 31 | **falta en 02 (Baja California)**. Probablemente esa carpeta viene de otra descarga |
| LITORAL_A / LITORAL_L | 17 | solo estados con costa |
| COLONIA_PUNTUAL | 15 | 02, 04, 09, 12, 14, 15, 16, 19, 20, 21, 23, 24, 29, 30, 31 |
| LIMITE_INTERNACIONAL | 11 | estados fronterizos |
| LINEA_METRO_L / LINEA_METRO_P | 7 | 05, 09, 14, 15, 19, 21, 22 (**capa nueva**, no estaba en BC) |

**Consecuencia:** el proceso de carga tiene que tolerar que a un estado le falte una capa. Además, el modelo necesita una tabla para el metro.

### 1.2 Volumen nacional

| Capa | Registros | Disco |
|---|---|---|
| NUMEROS_EXTERIORES | **8,864,204** | **5.9 GB** (68 % del total) |
| MANZANA | 2,502,184 | 893 MB |
| VIALIDAD | 2,278,577 | 630 MB |
| RASGO_COMPLEMENTARIO (A+L) | 334,486 | 163 MB |
| LOCALIDAD | 209,900 | — |
| ESCUELA | 159,300 | — |
| IGLESIA | 119,309 | — |
| COLONIA | 116,661 | 116 MB |
| PASTO | 110,333 | 34 MB |
| LAGOS/RIOS | 102,368 | 127 MB |
| EDIFICIO | 88,685 | — |
| BRECHA / TERRACERIA / VEREDA / PAVIMENTADA | 81,475 / 62,831 / 45,292 / 29,652 | — |
| SECCION | 73,268 | — |
| Puntos de interés (16 capas) | 563,571 | — |
| MUNICIPIO / DISTRITO_LOCAL / DISTRITO_FEDERAL | 2,477 / 679 / 300 | — |

**Estimación:** la base completa ocupará 10–15 GB con índices. Sin NUMEROS_EXTERIORES serían 3–5 GB.

### 1.3 Proyección: hay 5 zonas UTM distintas
Todos los archivos usan WGS 84 / UTM, pero **cada estado viene en su propia zona**:

| Zona (EPSG) | Estados |
|---|---|
| 11N (32611) | 02 |
| 12N (32612) | 03, 26 |
| 13N (32613) | 01, 06, 08, 10, 14, 18, 25, 32 |
| 14N (32614) | 05, 09, 11, 12, 13, 15, 16, 17, 19, 20, 21, 22, 24, 28, 29, 30 |
| 15N (32615) | 04, 07, 27 |
| 16N (32616) | 23, 31 |

**Decisión (obligatoria):** se guarda todo en **EPSG:4326**. Es la única forma de tener tablas nacionales. Para áreas y distancias se usa `geography` o `ST_Transform(geom, 6372)` (Lambert cónica de México, ITRF2008, INEGI). La zona de origen de cada estado se registra en `meta.carga.srid_origen`.

### 1.4 Codificación de texto: la regla es consistente
Se verificó con los bytes reales de los 1,596 `.DBF`:
- **Con `.cpg`:** se respeta lo que dice. Las 5 capas de límites (ENTIDAD, MUNICIPIO, DISTRITO_FEDERAL, DISTRITO_LOCAL, SECCION) dicen UTF-8 en los 32 estados. La excepción es `12 GUERRERO/OFICINA_MUNICIPAL`, que trae `.cpg` = ISO-8859-1 y también es correcto.
- **Sin `.cpg`:** siempre **Latin-1/CP1252** (824 archivos con acentos o Ñ; ninguno resultó estar en UTF-8).

GDAL lee el `.cpg` automáticamente. Para las capas sin `.cpg` hay que forzar `SHAPE_ENCODING=CP1252`.

### 1.5 Los esquemas son iguales, salvo detalles de forma
Se compararon los campos de cada capa en todos los estados. **Los tipos y longitudes coinciden.** Las diferencias son solo de forma:

| Diferencia | Ejemplos | Tratamiento |
|---|---|---|
| Mayúsculas/minúsculas en el nombre | `Caso_Captu` / `CASO_CAPTU`; `VALIDA` / `Valida` / `valida`; `PRO` / `Pro`; `ID` / `id`; VOCAL_EJECUTIVO_* en minúsculas en 12–22 | normalizar todo a minúsculas (`-lco LAUNDER=YES`) |
| Nombre del campo hash | `Geometry1_`, `Geometry2_`, `Geometry_s` | se descarta |
| Orden de los campos | MODULO tiene 24 órdenes distintos; VOCAL_*, LOCALIDAD, MANZANA… | mapear **por nombre**, nunca por posición |
| Longitud numérica | MANZANA.SECCION y MANZANA.MANZANA son N11 en el 15 (N6 en los demás) | sin efecto (todo pasa a `integer`) |
| **Campo duplicado `LOCALIDAD_`** | en VOCAL_*, uno es la clave numérica y otro el nombre (texto), y **el orden se invierte** en 14 y 28 | asignar **por tipo**: el numérico es `localidad` y el texto es `localidad_nombre` |

Además:
- El campo `ENTIDAD` de cada capa coincide siempre con el número de la carpeta.
- `GMRotation` siempre vale 0 y se descarta.

### 1.6 Llaves naturales (verificadas en los 32 estados)

| Tabla | Llave natural | Resultado |
|---|---|---|
| entidad | `entidad` | única (32) |
| municipio | `(entidad, municipio)` | única (2,477) |
| distrito_federal | `(entidad, distrito_f)` | única (300) |
| distrito_local | `(entidad, distrito_l)` | única (679) |
| seccion | `(entidad, seccion)` | única (73,268) |
| manzana | `(entidad, seccion, localidad, manzana)` | única (2,502,184) |
| limite_localidad | `(entidad, municipio, localidad)` | única (27,167) |
| localidad (puntos) | `(entidad, municipio, localidad)` | ❌ 368 repetidos |
| localidad (puntos) | `(entidad, municipio, localidad, seccion)` | ✅ única |
| modulo | `modulo` | ❌ 69 repetidos (56 en Querétaro). **No sirve como llave** |

**Interpretación de LOCALIDAD:** la capa de puntos no es "una fila por localidad". Es **una fila por cada combinación localidad–sección**: si una localidad abarca varias secciones, aparece una vez en cada una. Así se modela (§3.2).

**Integridad referencial:** en los 32 estados, todas las manzanas apuntan a una sección que existe, y todas las secciones apuntan a un municipio, distrito federal y distrito local que existen. **Las FK funcionan sin limpieza previa.**

### 1.7 Capas que vienen partidas por tipo de geometría

| Par | Atributos | Tratamiento |
|---|---|---|
| LAGOS / RIOS | `.DBF` idéntico en 32/32 | una tabla, dos geometrías |
| LITORAL_A / LITORAL_L | `.DBF` idéntico en 17/17 | ídem |
| RASGO_COMPLEMENTARIO_A / _L | `.DBF` idéntico en 32/32 | ídem |
| LINEA_METRO_L / LINEA_METRO_P | ⚠️ **el `.DBF` de `_L` está dañado** en los 7 estados | atributos desde `_P` y geometría de línea desde `_L`, unidas por número de registro |

**LINEA_METRO_L.DBF:** el encabezado declara un campo `GMRotation` de 19 bytes que no está en los datos. Cada registro mide 116 bytes, aunque el encabezado dice 135. Cualquier lector (GDAL incluido) va a desalinear las columnas a partir del segundo registro. Leído con el tamaño correcto, el contenido es idéntico registro por registro al de `LINEA_METRO_P.DBF` (verificado en los 7 estados). **Solución:** de `_L` se toma solo la geometría y el número de registro (FID). Los atributos se toman de `_P`.

### 1.8 Geometrías nulas (total nacional)

| Capa | Nulas / total |
|---|---|
| LAGOS / RIOS | 80,139 / 39,619 de 102,368 (cada registro trae una de las dos) |
| RASGO_COMPLEMENTARIO_A / _L | 185,731 / 198,784 de 334,486 |
| LITORAL_A / _L | 25 / 447 de 472 |
| LINEA_METRO_L / _P | 1,038 / 526 de 1,546 |
| COLONIA | 596 de 116,661 |
| FERROCARRIL | 53 de 917 |

Todos los polígonos se guardan como `MultiPolygon` y todas las líneas como `MultiLineString` (`-nlt PROMOTE_TO_MULTI`).

### 1.9 Calidad de campos
- **"SIN NOMBRE"** se usa en lugar de NULL: VIALIDAD 638,519 (28 %), LAGOS 36,789, VEREDA 20,619 y PUENTE.OBSERVACIO 10,139. **Se normaliza a NULL.**
- **MANZANA.DISPERSO y CASO_CAPTU:** en BC estaban vacíos, pero a nivel nacional sí tienen datos.
  - `DISPERSO` tiene 82,000 valores no vacíos ('0', '1', 'S', 'N' y basura como '"' o '|').
  - `CASO_CAPTU` tiene 213,000 valores distintos de 0.
  - **Se conservan**: `disperso` como texto crudo y `caso_captura` como entero.
- **NUMEROS_EXTERIORES:** `Tramo`, `Manzana` y `Vialidad` valen 0 en una parte grande de los registros: 82 % en BC, 57 % en GTO y 40 % en CDMX. Esos campos no son una FK confiable.
- **VIALIDAD.SENTIDO** trae valores fuera de lo esperado (-4, 3, 5, 9, 10 … 40). Parecen velocidades capturadas en el campo equivocado. Se guardan tal cual y se marcan con la validación de §5.

### 1.10 Campos codificados (valores nacionales)
**El significado de los códigos no viene en los datos.** Hay que sacarlo del diccionario de datos de la BGD del INE.

| Campo | Valores observados |
|---|---|
| SECCION.tipo | 2 (47,806), 3 (6,582), 4 (18,880) |
| DISTRITO_FEDERAL.tipo | 6–14 |
| MANZANA.STATUS, LOCALIDAD.STATUS | 1, 2 |
| LOCALIDAD.TIPO | 2 (34), 4 (209,866) |
| LOCALIDAD.CABECERA, LIMITE_LOCALIDAD.CABECERA | 1, 2, 3, 4, 9, 10, 19, 40, vacío |
| LIMITE_LOCALIDAD.TIPO | 2, 4 |
| VIALIDAD.TIPO | 1–22, 26, 27, 29 |
| VIALIDAD.CATEGORIA | 1, 2, 3 |
| VIALIDAD.SENTIDO | -1, 0, 1, 2 (más valores anómalos) |
| CONDICION (caminos) | 1–6, vacío |
| ESCUELA.TIPO | 0–6 |
| COLONIA.CLASIFICAC | 1–42 (41 valores) |
| LAGOS/RIOS.TIPO | 1–8 |
| LAGOS/RIOS.STATUS | 1, 2 |
| PUENTE.TIPO | 1, 2, 3 |
| AEROPUERTO.TIPO | 1, 2, 3 |
| MODULO.TIPO | 1–4 |
| ENTIDAD.circunscri | 1–5 |

---

## 2. Arquitectura

```
postgres
├── extensiones: postgis, pg_trgm, unaccent
├── staging    → copia 1:1 de cada shapefile, una tabla por estado y capa (e09_manzana, ...). Desechable.
├── cat        → catálogos de códigos
├── electoral  → entidad, municipio, distritos, sección, manzana
├── urbano     → localidades, colonias, manchas urbanas, números exteriores
├── vial       → calles, carreteras, ferrocarril, metro, puentes
├── poi        → puntos de interés (16 capas en una tabla)
├── fisico     → hidrografía, litoral, rasgos, pasto, límite internacional
├── ine        → módulos de atención y oficinas de vocales
└── meta       → bitácora de cargas
```

**Por qué hay una tabla de staging por estado:** como el orden y las mayúsculas de los campos cambian entre estados, cargar todos los estados directamente en una sola tabla es frágil. Es más seguro cargar `staging.eNN_<capa>` tal cual y luego pasarlo a la tabla final con un `INSERT ... SELECT` que nombra cada columna. Así, recargar un estado no afecta a los demás.

---

## 3. Modelo de tablas

Convenciones:
- Cada tabla tiene una PK sustituta `id bigint generated always as identity` y un `UNIQUE` sobre la llave natural.
- **`entidad smallint NOT NULL` en todas las tablas** y como primer componente de toda llave natural.
- La geometría es `geom geometry(<Tipo>, 4326)` con índice GIST.
- Se conservan `id_origen` y `control_origen` para rastrear cada registro hasta su shapefile, y `carga_id` apunta a `meta.carga`.
- **Particionado (opcional):** `manzana`, `vialidad` y `numero_exterior` pueden particionarse por lista de `entidad`. Así, recargar un estado es `TRUNCATE` de su partición, y las consultas por estado solo leen esa partición.

### 3.1 `electoral`

```
entidad ─┬─ municipio ─── limite_localidad
         ├─ distrito_federal
         ├─ distrito_local
         └─ seccion ──┬── manzana
                      └── localidad_seccion (puntos)
   (seccion → municipio, distrito_federal, distrito_local)
```

| Tabla | Origen | Geometría | Columnas propias |
|---|---|---|---|
| `entidad` | ENTIDAD | MultiPolygon | entidad (PK natural), nombre, circunscripcion, crc |
| `municipio` | MUNICIPIO | MultiPolygon | entidad, municipio, nombre |
| `distrito_federal` | DISTRITO_FEDERAL | MultiPolygon | entidad, distrito_f, tipo → cat |
| `distrito_local` | DISTRITO_LOCAL | MultiPolygon | entidad, distrito_l |
| `seccion` | SECCION | MultiPolygon | entidad, seccion, municipio, distrito_f, distrito_l, tipo → cat |
| `manzana` | MANZANA | MultiPolygon | entidad, municipio, seccion, localidad, manzana, status, disperso, caso_captura, distrito_f, distrito_l |

```sql
CREATE TABLE electoral.seccion (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entidad         smallint NOT NULL REFERENCES electoral.entidad (entidad),
  seccion         integer  NOT NULL,
  municipio       smallint NOT NULL,
  distrito_f      smallint NOT NULL,
  distrito_l      smallint NOT NULL,
  tipo            smallint REFERENCES cat.tipo_seccion,
  id_origen       integer,
  control_origen  integer,
  carga_id        integer REFERENCES meta.carga,
  geom            geometry(MultiPolygon, 4326) NOT NULL,
  UNIQUE (entidad, seccion),
  FOREIGN KEY (entidad, municipio)  REFERENCES electoral.municipio (entidad, municipio),
  FOREIGN KEY (entidad, distrito_f) REFERENCES electoral.distrito_federal (entidad, distrito_f),
  FOREIGN KEY (entidad, distrito_l) REFERENCES electoral.distrito_local (entidad, distrito_l)
);
CREATE INDEX ON electoral.seccion USING gist (geom);

CREATE TABLE electoral.manzana (
  id            bigint GENERATED ALWAYS AS IDENTITY,
  entidad       smallint NOT NULL,
  municipio     smallint NOT NULL,
  seccion       integer  NOT NULL,
  localidad     integer  NOT NULL,
  manzana       integer  NOT NULL,
  status        smallint,
  disperso      text,          -- crudo: '0','1','S','N', basura
  caso_captura  integer,
  distrito_f    smallint,
  distrito_l    smallint,
  id_origen     integer,
  carga_id      integer REFERENCES meta.carga,
  geom          geometry(MultiPolygon, 4326) NOT NULL,
  PRIMARY KEY (entidad, id),
  UNIQUE (entidad, seccion, localidad, manzana),
  FOREIGN KEY (entidad, seccion) REFERENCES electoral.seccion (entidad, seccion)
) PARTITION BY LIST (entidad);
-- CREATE TABLE electoral.manzana_09 PARTITION OF electoral.manzana FOR VALUES IN (9); ...
CREATE INDEX ON electoral.manzana USING gist (geom);
```

### 3.2 `urbano`

| Tabla | Origen | Geometría | Notas |
|---|---|---|---|
| `localidad_seccion` | LOCALIDAD | Point | entidad, municipio, localidad, seccion, nombre, tipo, cabecera, status, distrito_f, distrito_l. **UNIQUE `(entidad, municipio, localidad, seccion)`**. Es la parte de cada localidad que cae en una sección |
| `localidad` (vista) | derivada | — | `SELECT DISTINCT ON (entidad, municipio, localidad)` sobre la anterior, o un JOIN con `limite_localidad` |
| `limite_localidad` | LIMITE_LOCALIDAD | MultiPolygon | entidad, municipio, localidad, nombre, tipo, cabecera. UNIQUE `(entidad, municipio, localidad)` |
| `mancha_urbana` | MANCHA_URBANA | MultiPolygon | entidad, nombre |
| `colonia` | COLONIA + COLONIA_PUNTUAL | `geometry(Geometry, 4326)` | `representacion` ('poligono'/'punto'), entidad, municipio, nombre, clasificacion → cat, cp `char(5)`, otros_cp `text[]`. `geom` admite NULL (596) |
| `numero_exterior` | NUMEROS_EXTERIORES | MultiLineString | entidad, numero `text`, tramo, manzana_ref y vialidad_ref crudos (0 → NULL), valida, pro. **Se carga en una segunda fase** (ver §7) |
| `cabecera_municipal` | CABECERA_MUNICIPAL + CAPITAL | Point | `es_capital boolean`, entidad, municipio, localidad, localidad_nombre |

- `cp` es `char(5)` con ceros a la izquierda: `lpad(cp::text, 5, '0')`. Hay estados con CP que empiezan con 0 (CDMX: 01000 … 16999).
- `OTROS_CP` pasa a `text[]`, y "0" o vacío se convierten en `{}`.

### 3.3 `vial`

| Tabla | Origen | Geometría | Columnas |
|---|---|---|---|
| `vialidad` | VIALIDAD (2.28 M) | MultiLineString | nombre (NULL si "SIN NOMBRE"), categoria, tipo, sentido, velocidad. Particionable por entidad |
| `carretera` | AUTOPISTA + PAVIMENTADA + TERRACERIA + BRECHA + VEREDA | MultiLineString | **clase** ('autopista' … 'vereda'), nombre, condicion, velocidad |
| `ferrocarril` | FERROCARRIL | MultiLineString (NULL permitido) | nombre_estacion, nombre_via, condicion, observaciones |
| `metro` | LINEA_METRO_P + LINEA_METRO_L | `geom_estacion` Point + `geom_tramo` MultiLineString | entidad, nombre_estacion, linea, estaciones (texto "A - B"). Ver §1.7 |
| `puente` | PUENTE | MultiPolygon | tipo, observaciones |
| `superficie_vial` | ADOQUIN | MultiPolygon | material = 'adoquin' |

### 3.4 `poi`: una tabla para 16 capas de puntos (563,571 registros)

AEROPUERTO, CEMENTERIO, CENTRAL_AUTOBUS, CENTRO_COMERCIAL, CENTRO_CULTURAL, CENTRO_RECREATIVO, EDIFICIO, ESCUELA, HOSPITAL, IGLESIA, INSTALACIONES_BANCARIAS, INSTALACIONES_DEPORTIVAS, MERCADO, OFICINA_GUBERNAMENTAL, OFICINA_MUNICIPAL, PLAZA_MONUMENTO.

```sql
CREATE TABLE cat.categoria_poi (
  codigo       text PRIMARY KEY,     -- 'escuela', 'hospital', ...
  nombre       text NOT NULL,
  capa_origen  text NOT NULL         -- 'ESCUELA'
);

CREATE TABLE poi.punto_interes (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entidad         smallint NOT NULL,
  categoria       text NOT NULL REFERENCES cat.categoria_poi,
  subtipo         smallint,          -- ESCUELA.TIPO, AEROPUERTO.TIPO
  nombre          text,
  direccion       text,              -- solo EDIFICIO
  entrada         text,              -- solo EDIFICIO
  municipio       smallint,          -- enriquecido por cruce espacial
  seccion         integer,           -- enriquecido por cruce espacial
  id_origen       integer,
  control_origen  integer,
  carga_id        integer REFERENCES meta.carga,
  geom            geometry(Point, 4326) NOT NULL
);
CREATE INDEX ON poi.punto_interes USING gist (geom);
CREATE INDEX ON poi.punto_interes (entidad, categoria);
CREATE INDEX ON poi.punto_interes USING gin (nombre gin_trgm_ops);
```

### 3.5 `fisico`

| Tabla | Origen | Geometría |
|---|---|---|
| `hidrografia` | LAGOS + RIOS | `geom_poligono` + `geom_linea`; nombre, tipo, status |
| `litoral` | LITORAL_A + LITORAL_L | `geom_poligono` + `geom_linea` |
| `rasgo_complementario` | RASGO_COMPLEMENTARIO_A + _L | `geom_poligono` + `geom_linea`; descripcion |
| `pasto` | PASTO | MultiPolygon |
| `limite_internacional` | LIMITE_INTERNACIONAL | MultiLineString |

```sql
CREATE TABLE fisico.hidrografia (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entidad        smallint NOT NULL,
  nombre         text,
  tipo           smallint REFERENCES cat.tipo_hidrografia,
  status         smallint,
  id_origen      integer,
  control_origen integer,
  carga_id       integer REFERENCES meta.carga,
  geom_poligono  geometry(MultiPolygon, 4326),
  geom_linea     geometry(MultiLineString, 4326)
);
CREATE INDEX ON fisico.hidrografia USING gist (geom_poligono);
CREATE INDEX ON fisico.hidrografia USING gist (geom_linea);
```

La unión de cada par se hace por número de registro. En los tres pares de §1.7 que tienen `.DBF` idéntico, el registro N de `_A` y el registro N de `_L` son el mismo elemento.

### 3.6 `ine`

| Tabla | Origen | Columnas |
|---|---|---|
| `modulo_atencion` | MODULO (557) | entidad, distrito, municipio, localidad, seccion, manzana, modulo (clave **no única**), tipo, domicilio, dias_atencion, horario, referencia, cp, observaciones, imagen |
| `oficina_vocal` | VOCAL_DISTRITAL_DEL_RFE, VOCAL_EJECUTIVO_DISTRITAL, VOCAL_ESTATAL_DEL_RFE, VOCAL_EJECUTIVO_ESTATAL | **ambito** ('distrital'/'estatal'), **tipo_vocal** ('rfe'/'ejecutivo'), entidad, distrito, municipio, seccion, localidad, localidad_nombre, manzana, calle_numero, colonia, cp, telefono, fax |

### 3.7 `cat` (catálogos)
Cada catálogo es una tabla `(codigo smallint PK, descripcion text)`, una por dominio de §1.10:

`tipo_seccion`, `tipo_distrito`, `status_registro`, `tipo_localidad`, `cabecera`, `tipo_vialidad`, `categoria_vialidad`, `sentido_vialidad`, `condicion_camino`, `tipo_escuela`, `clasificacion_colonia`, `tipo_hidrografia`, `tipo_puente`, `tipo_aeropuerto`, `tipo_modulo`, `categoria_poi`.

Al principio se llenan con los códigos observados en los 32 estados y `descripcion = NULL`. Las descripciones se completan con el diccionario oficial.

### 3.8 `meta`

```sql
CREATE TABLE meta.carga (
  id            serial PRIMARY KEY,
  entidad       smallint NOT NULL,
  carpeta       text NOT NULL,         -- '09 CIUDAD DE MEXICO'
  archivo_zip   text,                  -- 'bgde_11_.zip'
  fecha_corte   date,
  srid_origen   integer NOT NULL,      -- 32614
  capas_cargadas text[],
  capas_faltantes text[],              -- p. ej. {ADOQUIN, FERROCARRIL}
  cargado_en    timestamptz DEFAULT now(),
  notas         text
);
```

---

## 4. Mapeo shapefile → tabla destino

| Shapefile(s) | Tabla destino | Transformación clave |
|---|---|---|
| ENTIDAD, MUNICIPIO, DISTRITO_FEDERAL, DISTRITO_LOCAL, SECCION | electoral.* | numéricos `N18/N24.15` → `integer` |
| MANZANA | electoral.manzana | `caso_captu` → caso_captura; disperso crudo |
| LOCALIDAD | urbano.localidad_seccion | llave con sección |
| LIMITE_LOCALIDAD | urbano.limite_localidad | — |
| MANCHA_URBANA | urbano.mancha_urbana | — |
| COLONIA, COLONIA_PUNTUAL | urbano.colonia | unir; cp → char(5); otros_cp → text[] |
| NUMEROS_EXTERIORES | urbano.numero_exterior | fase 2; 0 → NULL |
| CABECERA_MUNICIPAL, CAPITAL | urbano.cabecera_municipal | `es_capital`; `LOCALIDAD_` por tipo |
| VIALIDAD | vial.vialidad | "SIN NOMBRE" → NULL |
| AUTOPISTA, PAVIMENTADA, TERRACERIA, BRECHA, VEREDA | vial.carretera | `clase` |
| FERROCARRIL | vial.ferrocarril | — |
| LINEA_METRO_P + LINEA_METRO_L | vial.metro | **atributos de `_P`**, geometría de `_L` por FID |
| PUENTE | vial.puente | — |
| ADOQUIN | vial.superficie_vial | — |
| 16 capas de puntos | poi.punto_interes | `categoria` |
| LAGOS + RIOS | fisico.hidrografia | unir por FID |
| LITORAL_A + LITORAL_L | fisico.litoral | unir por FID |
| RASGO_COMPLEMENTARIO_A + _L | fisico.rasgo_complementario | unir por FID |
| PASTO | fisico.pasto | — |
| LIMITE_INTERNACIONAL | fisico.limite_internacional | — |
| MODULO | ine.modulo_atencion | — |
| 4 capas VOCAL_* | ine.oficina_vocal | `ambito` + `tipo_vocal`; `LOCALIDAD_` por tipo |

**Resultado:** 54 capas × 32 estados quedan en **~26 tablas** más los catálogos.

---

## 5. Validaciones después de cargar

```sql
-- conteos contra el origen (por estado)
SELECT entidad, count(*) FROM electoral.manzana GROUP BY 1 ORDER BY 1;   -- total 2,502,184
SELECT count(*) FROM electoral.seccion;                                  -- 73,268

-- geometrías inválidas (ArcGIS suele dejar auto-intersecciones)
SELECT entidad, count(*) FROM electoral.seccion WHERE NOT ST_IsValid(geom) GROUP BY 1;
-- reparación: SET geom = ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))

-- manzanas fuera de su sección declarada
SELECT m.entidad, count(*) FROM electoral.manzana m
JOIN electoral.seccion s USING (entidad, seccion)
WHERE NOT ST_Intersects(s.geom, ST_PointOnSurface(m.geom)) GROUP BY 1;

-- distritos de manzana distintos a los de su sección
SELECT count(*) FROM electoral.manzana m JOIN electoral.seccion s USING (entidad, seccion)
WHERE m.distrito_f <> s.distrito_f OR m.distrito_l <> s.distrito_l;

-- sentido de vialidad fuera de dominio
SELECT entidad, sentido, count(*) FROM vial.vialidad
WHERE sentido NOT IN (-1,0,1,2) GROUP BY 1,2;

-- secciones que se salen de su municipio (control topológico)
SELECT s.entidad, s.seccion FROM electoral.seccion s
JOIN electoral.municipio m USING (entidad, municipio)
WHERE ST_Area(ST_Difference(s.geom, m.geom)::geography) > 1000;
```

**Enriquecimiento espacial:**
- `poi.punto_interes.municipio` y `.seccion` se llenan con `ST_Intersects(punto, seccion.geom)`.
- `urbano.numero_exterior → manzana` se calcula por intersección o por la manzana más cercana.

---

## 6. Proceso de carga

1. Instalar dependencias: `brew install gdal postgresql@16 postgis` (o usar Postgres en Docker con `postgis/postgis`).
2. Crear esquemas, catálogos, tablas finales y particiones (`sql/01_schema.sql` …).
3. Para cada carpeta `NN NOMBRE/` y cada capa presente, cargar a staging:
   ```bash
   ogr2ogr -f PostgreSQL PG:"dbname=paz" "09 CIUDAD DE MEXICO/MANZANA.shp" \
     -nln staging.e09_manzana -lco GEOMETRY_NAME=geom -lco LAUNDER=YES \
     -lco FID=fid -t_srs EPSG:4326 -nlt PROMOTE_TO_MULTI \
     --config SHAPE_ENCODING CP1252        # omitir si la capa tiene .cpg
   ```
   - En `LINEA_METRO_L` se carga **solo la geometría**: `-sql "SELECT FID FROM LINEA_METRO_L"` o `-select ""`.
   - El origen no necesita `-s_srs`, porque GDAL lo toma del `.prj` de cada estado.
4. Pasar de staging a las tablas finales con `INSERT ... SELECT` explícitos por capa (§4).
5. Registrar la carga en `meta.carga` (capas presentes y faltantes, SRID de origen).
6. Correr las validaciones de §5 y los enriquecimientos.
7. Ejecutar `VACUUM ANALYZE` y luego `DROP SCHEMA staging CASCADE`, o solo borrar las tablas del estado.

Todo esto se automatiza con un script (Python o bash) que recorra las 32 carpetas y que también permita recargar un solo estado.

---

## 7. Decisiones abiertas

1. **NUMEROS_EXTERIORES:** ¿se necesita? Representa el 68 % del volumen (5.9 GB, 8.9 M de líneas) y sus FK son poco confiables. **Propuesta:** dejarlo para una segunda fase.
2. **Diccionario de códigos:** ¿tienes el documento de la BGD del INE para TIPO, STATUS, CONDICION, CLASIFICAC, etc.?
3. **Registros sin geometría** (~600 colonias, 53 tramos de ferrocarril y rasgos/hidrografía sin ninguna de las dos geometrías): ¿se conservan con NULL o se descartan?
4. **Baja California:** su carpeta no trae VOCAL_*_ESTATAL. ¿Viene de una descarga anterior? Valdría la pena bajarla otra vez del mismo origen que las demás para tener la misma versión.
5. **Particionado por entidad:** ¿lo aplicamos en manzana, vialidad y numero_exterior? Se recomienda si se recargarán estados por separado.
6. **Uso final:** si es para mapas web, conviene planear vistas simplificadas (`ST_SimplifyPreserveTopology`) o vector tiles (`ST_AsMVT`) para manzana y vialidad.
