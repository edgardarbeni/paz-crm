# D-18 · Importador

- **Estado:** Aceptada
- **Área:** Geografía electoral

Python + **pyogrio**:
- Lee los 7z/shapefiles y los catálogos (txt/xlsx).
- Normaliza cada registro: encoding según `.cpg` o CP1252, `SIN NOMBRE` → NULL, mapeo por nombre de campo, reproyección a EPSG:4326 y `PROMOTE_TO_MULTI`.
- Valida registro por registro.
- Carga con `COPY` a una tabla temporal y hace **upsert por llave natural**.
- Modo `--dry-run`, reporte de errores y advertencias por registro (`import_errors`) e idempotencia (archivo + hash SHA-256).

(Descartado: ogr2ogr + SQL, porque solo reporta errores por lote y depende del binario de GDAL.)
