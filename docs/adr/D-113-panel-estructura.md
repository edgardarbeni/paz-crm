# D-113 · Panel de la estructura del partido (fase 7; cierra el módulo)

- **Estado:** Aceptada (2026-10-31)
- **Área:** Estructura del partido · Panel

Pantallas del panel en el menú «Estructura del partido». Cada una se muestra según el permiso; la
API vuelve a validar nivel y alcance (D-101, D-105).

| Pantalla | Ruta | Permiso | Qué hace |
|---|---|---|---|
| Órganos y cargos | `/structure/bodies` | `body.read` | Órganos en el alcance, con filtros por nivel, estado y disueltos; instalar un comité distrital o municipal (`body.write`) |
| Detalle de órgano | `/structure/bodies/{id}` | `appointment.read` | Asientos con su titular o la vacante; nombrar, terminar, historial, dar o quitar acceso, elegir la fuente del Presídium; disolver un comité |
| Coordinaciones | `/structure/coordinations` | `coordination.read` | Lista y creación con su territorio (distritos o secciones) |
| Detalle de coordinación | `/structure/coordinations/{id}` | `coordination.read` | Editar el territorio con fecha (el alcance de los titulares se ajusta), cerrar y equipo (asientos) |
| Catálogo estatutario | `/structure/catalog` | `body.read` | Órganos y cargos con fundamento, órgano que elige, periodo y rol; agregar cargos e incompatibilidades (`catalog.manage`) |
| Territorio por resolver | `/structure/territory` | `catalog.manage`, nivel nacional | Bandeja tras un cambio de marco: reasignar o disolver comités, aceptar o cerrar coordinaciones |

Además:
- **Ficha de persona:** tarjeta «Cargos en el partido», con sus cargos vigentes en órganos
  visibles.
- **Reasignar el crédito de una casa:** busca entre todos los cargos ocupados por nombre del
  cargo o del titular, con `GET /party-structure/positions/held` (nuevo, `appointment.read` y
  órganos visibles). Antes solo ofrecía los cargos propios (D-112).
- **Nombrar con acceso:** en el mismo diálogo, si el usuario tiene `grant_access`. Si el acceso
  no se puede dar, el panel avisa por qué (`access_pending`) y el nombramiento queda registrado.

**Módulo completo.** Con esta fase quedan implementadas las fases 0 a 7 de
[party-structure.md](../modules/party-structure.md) (D-101 a D-113).

Queda fuera, como dice la ficha: metas y tableros por cargo, y flujos de elección o aprobación de
órganos. Las incompatibilidades iniciales las define jurídico (D-105).
