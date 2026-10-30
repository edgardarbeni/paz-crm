# D-103 · Crédito de las Casas de Paz a asientos de estructura (reemplaza en parte D-92 y D-96)

- **Estado:** Aceptada (2026-10-30, con cambios de Darío a la ficha)
- **Área:** Movimiento de Paz · Estructura del partido

Reemplaza los puntos «Coordinadores por zona» y «Sin zona» de
[D-92](D-92-reglas-negocio-movimiento-paz.md) y el cálculo del crédito de
[D-96](D-96-ajustes-implementacion-casas.md). Se mantienen el resto de D-92, que el crédito se
fija al abrir o enlazar, y la reasignación con motivo e historial.

**Regla nueva** (respuesta de Darío del 2026-10-30; cambia lo que dice
[party-structure.md](../modules/party-structure.md), «Cambios al Movimiento de Paz»):
- **Cualquier integrante activo del MP** que abre una casa se lleva el crédito, sea del nivel que
  sea. Ya no se busca un Embajador en la cadena, y la ficha ya no deja pendientes las casas que
  abre un Pacificador, Promotor o Mensajero.
- Solo cuentan para una **meta** de casas los niveles que la tienen (Embajador y Constructor). Las
  casas acreditadas a los demás niveles cuentan en las estadísticas.
- La **bandeja de casas por enlazar** recibe las casas que se abren sin un integrante ni un asiento
  que reciba el crédito, y las que quedan pendientes por la migración.
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
- `peace_movement.house.reassign_credit` (existente): reasignar con motivo, ahora hacia
  **cualquier integrante activo** o un asiento. Hoy solo acepta Embajadores.

**Migración de datos (corrige el supuesto de la ficha)**
- Una casa acreditada a un usuario coordinador de zona pasa al asiento vigente de esa persona si
  tiene exactamente uno; si no, queda pendiente en la bandeja.
- La ficha dice que las casas acreditadas a un Promotor o Mensajero conservan su crédito, pero la
  regla vigente nunca les dio crédito. El caso real son las casas de un Embajador que después
  bajó de nivel: conservan su crédito, porque D-92 lo fija al abrir.

**Pendiente de confirmar:** qué pasa con el crédito cuando el integrante acreditado se da de baja
del MP. Por D-92 no se recalcula, así que la casa conservaría el crédito; la alternativa es que
pase a la bandeja.

*Motivo:* el crédito es de quien abre la casa (o del cargo, si la abre la estructura), no de una zona.
