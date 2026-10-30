# D-103 · Crédito de las Casas de Paz a asientos de estructura (reemplaza en parte D-92 y D-96)

- **Estado:** Propuesta (2026-10-30)
- **Área:** Movimiento de Paz · Estructura del partido

Reemplaza los puntos «Coordinadores por zona» y «Sin zona» de
[D-92](D-92-reglas-negocio-movimiento-paz.md) y el cálculo del crédito de
[D-96](D-96-ajustes-implementacion-casas.md). Se mantienen el resto de D-92, que el crédito se
fija al abrir o enlazar, y la reasignación con motivo e historial.

**Regla nueva** ([party-structure.md](../modules/party-structure.md), «Cambios al Movimiento de Paz»):
- Si abre la casa un **Embajador o un Constructor de Paz** activo, el crédito es suyo.
- Si la abre un Pacificador, Promotor o Mensajero, queda **pendiente** en la bandeja de casas por
  enlazar. Ya no se busca un Embajador en la cadena.
- Cualquier **asiento** de estructura con nombramiento vigente puede abrir una casa o enlazar una
  pendiente, sin importar la geografía. El crédito es del asiento y lo hereda el siguiente titular.
- `credited_user_id` se reemplaza por `credited_position_id`. A lo más uno de los dos créditos
  existe.
- Se retiran `zone_coordinators`, `zone_coordinator_nodes` y `zone_coordinator_sections`, junto
  con sus endpoints, su pantalla y su permiso.
- El Constructor tiene meta de casas: semilla nacional de 1 en `level_goals.house_goal`, medida
  con casas consolidadas. La columna ya existe; solo cambia la semilla.

**Permisos**
- `peace_movement.house.link` (nuevo): abrir o enlazar con crédito a un asiento propio.
- `peace_movement.house.reassign_credit` (existente): reasignar con motivo, ahora hacia un
  Embajador, un Constructor o un asiento. Hoy solo acepta Embajadores.

**Migración de datos (corrige el supuesto de la ficha)**
- Una casa acreditada a un usuario coordinador de zona pasa al asiento vigente de esa persona si
  tiene exactamente uno; si no, queda pendiente en la bandeja.
- La ficha dice que las casas acreditadas a un Promotor o Mensajero conservan su crédito, pero la
  regla vigente nunca les dio crédito. El caso real son las casas de un Embajador que después
  bajó de nivel: conservan su crédito, porque D-92 lo fija al abrir.

*Motivo:* el crédito de las casas sigue al cargo, no a la persona ni a una zona.
