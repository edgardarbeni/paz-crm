# D-34 · Alcance geográfico

- **Estado:** Aceptada
- **Área:** Identidad, acceso y auditoría

- El alcance de un usuario se traduce en el **conjunto de secciones** de sus nodos asignados (tabla derivada `user_scope_sections`).
- **Geografía:** ve todo lo que toca esas secciones.
- **Candidaturas:** **edita** las cuya geografía queda contenida por completo en su alcance, y ve **en solo lectura** las que solo se traslapan.
- Estado y circunscripción contienen todo lo de abajo.
- El filtro se aplica en la capa de repositorio (consulta), no solo en los endpoints.
