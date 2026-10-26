# D-41 · Modelo de datos aprobado

- **Estado:** Aceptada
- **Área:** Modelo de datos

El usuario aprobó [`reference/data-model.md`](../reference/data-model.md) el 2026-10-24, incluidos sus 7 puntos:
1. Módulo `people` separado de `candidacies`.
2. Enumeraciones como `text + CHECK`.
3. Postulación + fórmula como estructura única para todos los cargos, con la composición de planillas en `slate_parent_office_type_id`.
4. `section_parts` para el punto-en-polígono.
5. `user_scope_sections` como conjunto derivado para filtrar por alcance.
6. `framework_id` en todas las tablas geográficas, con FKs compuestas.
7. Remapeo por llave natural de alcances y domicilios al activar un nuevo marco.
