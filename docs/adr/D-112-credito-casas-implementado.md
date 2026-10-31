# D-112 · Crédito de las Casas de Paz a la estructura: implementación (fase 6; detalla D-103 y D-105)

- **Estado:** Aceptada (2026-10-31)
- **Área:** Movimiento de Paz · Estructura del partido

Cómo quedó [D-103](D-103-credito-casas-estructura.md) con las respuestas de
[D-105](D-105-reglas-estructura-confirmadas.md) (migración `0024`).

**Al abrir una casa**
- La puede abrir un pacificador (`opened_by_member_id`, ahora opcional) **o** un asiento de la
  estructura que ocupa quien la registra (`opened_by_position_id`); no los dos (422).
- El crédito es de quien la abre:
  - si es un pacificador, de cualquier nivel;
  - si es un asiento, lo hereda quien ocupe ese asiento después.
- Abrir con un asiento exige `peace_movement.house.link` y ocupar ese cargo. En ese caso no se
  exige que la casa caiga en el alcance geográfico («sin importar la geografía»).
- Si no la abre nadie, queda con crédito pendiente.

**Bandeja de casas por enlazar**
- `GET /houses/pending-credit` lista las casas vigentes sin crédito de todo el país para quien
  tiene `house.link`.
- `POST /houses/{id}/link` la enlaza a un cargo propio: 409 si ya tiene crédito, 403 si el cargo
  no es tuyo.
- Mis cargos: `GET /party-structure/my-positions`.

**Reasignación:** a mano y con motivo (`house.reassign_credit`), hacia un pacificador activo de
cualquier nivel o hacia un asiento **ocupado**; uno vacante responde 409. El historial
(`peace_house_credit_changes`) gana `from_position_id` y `to_position_id`. Las columnas de
usuario quedan como historia anterior a D-103.

**Baja del acreditado (D-105):** si el pacificador acreditado deja el movimiento o se da de baja
por ARCO, la casa vuelve a la bandeja y queda en el historial.

**Retiro de los coordinadores de zona.**
- Se eliminaron sus tres tablas, los endpoints `/zone-coordinators` y la pestaña de configuración
  del panel.
- **Migración de datos:** una casa acreditada a un usuario pasó a su asiento si esa persona
  ocupaba exactamente un cargo (vía `person_accounts`); si no, quedó en la bandeja. Los dos casos
  dejan su registro en el historial.

**Meta del Constructor:** `level_goals.house_goal = 1` nacional para el Constructor de Paz,
ajustable por estado; se mide con casas consolidadas, como la del Embajador.

**Panel**
- La ficha de una casa muestra el cargo acreditado.
- La reasignación ofrece un pacificador o uno de tus cargos. La selección de cualquier asiento
  llegará con el panel de la estructura (fase 7).
- La pantalla de apertura permite abrir con un cargo propio.
- Hay una pantalla nueva, «Casas por enlazar».

**Dependencia entre módulos.** El MP depende de la estructura: FKs a `party_structure.positions`
y uso de `party_structure.access` para los cargos de un usuario. La estructura no depende del MP.
