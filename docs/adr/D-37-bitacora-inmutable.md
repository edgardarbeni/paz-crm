# D-37 · Bitácora inmutable

- **Estado:** Aceptada
- **Área:** Identidad, acceso y auditoría
- **Detallada por:** [D-45](D-45-implementacion-bitacora.md)

Tabla **append-only** particionada por mes y escrita con un rol de BD que solo puede hacer `INSERT` (sin UPDATE ni DELETE, reforzado con trigger). Cada entrada guarda el **hash de la anterior** (cadena verificable con un comando). Los meses viejos se pueden exportar a almacenamiento externo. Los valores sensibles en `before`/`after` se guardan enmascarados o cifrados.
