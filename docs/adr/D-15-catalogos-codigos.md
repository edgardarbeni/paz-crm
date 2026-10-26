# D-15 · Catálogos de códigos

- **Estado:** Aceptada
- **Área:** Geografía electoral
- **Ampliada por:** [D-59](D-59-mapeos-codigos-verificados.md)

Las descripciones se derivan de los **catálogos oficiales del INE**, cruzándolos con la BGD, y se guarda la fuente. Un código sin evidencia queda con descripción `NULL`, editable desde el panel. No se inventan significados.
Mapeos verificados con Aguascalientes (corte dic-2025), con coincidencia del 100 % registro por registro:

| Campo BGD | Código → texto INE | Evidencia |
|---|---|---|
| `SECCION.tipo` | 2 → URBANO(A), 3 → MIXTO(A), 4 → RURAL | 736/736 vs Catálogo de Secciones |
| `MANZANA.status` | 1 → `C`, 2 → `*` | 25,482/25,482 vs Catálogo de Manzanas |
| `LOCALIDAD.tipo` | 4 → RURAL | 1,729/1,729 vs Catálogo de Localidades con Sección |

Pendiente: el significado de `C` y `*` (el Catálogo de Productos Cartográficos habla de "habilitada / deshabilitada", pero no dice cuál es cuál) y el código 2 de localidad (presumiblemente URBANO).
