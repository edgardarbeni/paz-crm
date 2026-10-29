# D-95 · Ajustes de implementación de la fase 1 del Movimiento de Paz (pacificadores)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz

Precisiones al implementar la fase 1 sobre [peace-movement.md](../modules/peace-movement.md),
[D-82](D-82-consentimiento-aviso-movimiento-paz.md), [D-83](D-83-alcance-por-rama.md),
[D-91](D-91-jerarquia-reclutamiento-ltree.md) y [D-92](D-92-reglas-negocio-movimiento-paz.md).

- **`people` no depende del MP.** `people/hooks.py` expone `on_person_deleted` y
  `on_address_changed`; el MP los registra al arrancar con `ModuleSpec.setup`. La baja ARCO marca
  `withdrawn` y el cambio de domicilio actualiza `state_id` y `section_id` del pacificador, en la
  misma transacción. `people.build_person` crea sin confirmar, para que la inscripción (persona,
  consentimiento y pacificador) sea una sola transacción.
- **Catálogo de avisos en `people`** (`privacy_notices`), publicado con el permiso nuevo
  `people.notice.manage` (admin). `paz people sample-notice` publica un texto de ejemplo marcado
  con `is_sample`, solo fuera de staging y producción.
- **Historial de metas sin `btree_gist`.** Un índice único parcial garantiza una sola meta vigente
  (`valid_to` nulo) por nivel y estado; fijar otra cierra la vigente el día anterior. Si empieza
  el mismo día, corrige la vigente en lugar de abrir otro periodo; una fecha anterior a la vigente
  responde 409.
- **Permisos sin códigos nuevos.**
  - Registrar la salida del movimiento (`left`) usa `peace_movement.member.validate`.
  - Asignar ramas usa `identity.user.assign_scopes` y leerlas `identity.user.read`: son
    alcances de usuario.
- **Detalle de pacificadores fuera de su alcance:** 404, como `people`. El detalle de un nodo
  `withdrawn` sigue disponible con la persona dada de baja (y después anonimizada).
- **Persona existente fuera del alcance:** inscribirla responde 403, la regla de D-66, salvo
  dentro de una rama.
- **Rechazo con reclutas:** una inscripción pendiente con reclutas no se rechaza (409); primero se
  reasignan.
- **`network_changes` empieza a llenarse en esta fase** (alta, validación, rechazo, salida, baja,
  cambio de nivel o de domicilio, reasignación), aunque el proceso que la consume llega en la
  fase 3. Mientras tanto, el detalle cuenta los reclutas directos al vuelo, por el índice de
  `recruited_by_member_id`; la red completa se reporta con los agregados.
- **Alerta de profundidad:** se registra en el log (`peace_movement_depth_alert`) al inscribir por
  debajo de `settings.depth_alert_threshold`.

*Motivo:* mantener a `people` independiente, evitar una extensión más y no inventar permisos que
la ficha no pide. (Descartadas: `EXCLUDE` con `btree_gist` para las vigencias y llamar al MP
directamente desde `people`.)
