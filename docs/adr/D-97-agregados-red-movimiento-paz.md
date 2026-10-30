# D-97 · Agregados de la red del Movimiento de Paz (fase 3)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz · Rendimiento

Cómo se cumplen «sin recursión en lecturas», «sin contención en la cima» y «las estadísticas
reflejan una inscripción en menos de 5 minutos» de [peace-movement.md](../modules/peace-movement.md),
con [D-84](D-84-tareas-periodicas.md), [D-90](D-90-auditoria-escrituras-masivas.md) y
[D-91](D-91-jerarquia-reclutamiento-ltree.md).

- **Incremental, de abajo hacia arriba** (`paz peace-movement aggregate`, cada minuto).
  - Toma lotes de `network_changes` y junta las cadenas de ancestros de sus rutas.
  - Recalcula esos nodos del más profundo al más alto: cada nodo suma los contadores de sus
    reclutas directos (red activa, por nivel, directos activos y pendientes) más sus casas
    acreditadas.
  - Solo lee hijos directos, por el índice de `recruited_by_member_id`, así que nunca cuenta
    una red completa y la cima recibe una sola actualización por lote.
  - Los nodos `left` o `withdrawn` no cuentan, pero su red sí sube.
- **Completo, nocturno** (`--full`, 03:45 UTC).
  - Recalcula todo «explotando» la ruta de cada activo en sus ancestros (etiquetas
    `tree_id`) y agrupando.
  - Reconstruye los conteos por sección y por día y revisa la consolidación de las casas
    contra las metas vigentes.
  - Corrige cualquier desviación del incremental.
- **Conteos por sección** (`member_section_counts`): activos por sección y nivel. Las
  estadísticas geográficas suman secciones en lugar de contar pacificadores al vuelo (de
  779 ms a 4 ms con un millón). Un cambio de domicilio lleva la sección anterior en el evento.
- **Conteos por día** (`enrollment_daily_counts`): inscripciones validadas (activas, con
  salida o baja) por día de inscripción, nivel **actual** y sección. Miden crecimiento, no el
  nivel con que se inscribieron.
- **Las tareas no usan el límite de la API:** fijan su propio `statement_timeout` (5 minutos el
  incremental, 30 el completo) porque `PAZ_DATABASE_STATEMENT_TIMEOUT_MS` (15 s) cancelaría
  el recálculo de una red grande.
- **Bitácora:** las tablas derivadas no se auditan por fila; cada corrida deja una entrada
  (`network_aggregated`, `network_rebuilt`), como D-90.
- **Comandos del módulo:** `ModuleSpec.cli` monta `paz peace-movement …` sin editar el CLI del
  núcleo (amplía [D-94](D-94-infraestructura-scheduler-s3-modulos.md)).
- **Carga sintética** (`seed-load`, solo desarrollo y pruebas): COPY directo, sin bitácora, para
  medir con un millón de pacificadores.
- **Exportación CSV:** hasta 50,000 filas (409 si se pasa); queda en `audit.access_log` con los
  filtros y si iba sin enmascarar.

*Motivo:* la suma por hijos directos es exacta, acotada por la profundidad y barata en la cima.
El recálculo completo con ancestros explotados tarda un minuto con un millón de nodos.
(Descartadas: contar con `path <@` en cada recálculo, que en la cima recorre la red entera;
deltas +1/−1 por evento, que se complican con reasignaciones y cambios de estatus; un trigger
por fila, que serializa las altas en la cima.)
