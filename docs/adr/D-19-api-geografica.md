# D-19 · API geográfica

- **Estado:** Aceptada
- **Área:** Geografía electoral

- **Búsqueda por clave INE flexible:** acepta formatos con o sin ceros y separadores (`09-0123`, `9 123`, `090123`; municipio `09-005`; distrito `09-12`). Se normaliza a (estado, clave) y se puede filtrar por nivel. También hay búsqueda por nombre con `pg_trgm` + `unaccent`.
- **Punto-en-polígono:** se resuelve sobre `section_parts` (secciones subdivididas con `ST_Subdivide`) y luego se suben los ancestros por FK, para cumplir < 50 ms p95.
- **Vector tiles:** endpoint MVT (`/api/v1/geography/tiles/{level}/{z}/{x}/{y}.mvt`) con `ST_AsMVT`, simplificación por zoom y caché en Redis. El panel incluye un **visor de mapa básico** (MapLibre GL).
