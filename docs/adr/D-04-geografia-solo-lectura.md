# D-04 · Geografía de solo lectura (excepción a CLAUDE.md)

- **Estado:** Aceptada
- **Área:** Geografía electoral

Las tablas geográficas solo cambian por importación. Llevan `created_at`, `updated_at`, `import_run_id` e `is_active`, y **no llevan `deleted_at`**: lo que desaparece del origen se marca `is_active = false`.
*Motivo:* el soft-delete no tiene sentido en datos de referencia oficiales. (Descartado: las tres columnas en todo; geografía editable desde el panel.)
