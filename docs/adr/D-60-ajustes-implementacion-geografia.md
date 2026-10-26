# D-60 · Ajustes de implementación de la geografía (sobre [`reference/data-model.md`](../reference/data-model.md) §1)

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Importaciones:**
  - `import_errors` se llama `import_issues`, porque guarda errores y advertencias.
  - `import_runs.counts` (jsonb por tabla) reemplaza las columnas de conteo.
  - `triggered_by` es texto: hoy las importaciones se lanzan por CLI ([D-42](D-42-plan-fases-aprobado.md)).
- **Relación colonia–sección:** `neighborhood_sections.source` reemplaza a `match_method` ([D-57](D-57-relacion-colonia-seccion-desde-catalogo-ine.md)).
- **Particiones de manzanas:** la función `geography.ensure_block_partition(framework_id)` crea una partición por marco al importar. Alembic las ignora (`env.py`).
- **Upserts:** distinguen insertado de actualizado con `RETURNING old.id IS NULL` (PostgreSQL 18), que funciona también sobre la tabla particionada.
- **Desactivación:** solo se marcan inactivos registros de capas que cargaron sin errores. Si una capa trae errores, se omite la desactivación y se avisa con `deactivation_skipped`, para que un archivo dañado nunca desactive datos válidos.
- **Alcance vacío:** un usuario sin alcance no ve geografía (denegación por defecto), y un alcance `national` equivale a sin restricción. Los usuarios sin alcance sí son administrables por cualquier admin con el permiso, para poder configurarlos.
