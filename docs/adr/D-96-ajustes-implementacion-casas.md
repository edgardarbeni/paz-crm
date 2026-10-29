# D-96 · Ajustes de implementación de la fase 2 del Movimiento de Paz (Casas de Paz)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz

Precisiones al implementar las Casas de Paz sobre [peace-movement.md](../modules/peace-movement.md),
[D-85](D-85-ubicacion-casas-paz.md) y [D-92](D-92-reglas-negocio-movimiento-paz.md).

- **Ubicación (D-85).**
  - El punto exacto viaja cifrado junto con la calle (`address_ciphertext`). La sección, el
    municipio y el estado se calculan con ese punto (`locate`) antes de redondearlo.
  - `location` guarda el punto con 3 decimales (unos 110 m), con índice GiST.
  - La calle y el punto exacto solo salen con `people.person.read_sensitive`. Cada detalle
    queda en `audit.access_log`.
- **Consentimiento para publicar la ubicación.** Es un consentimiento de `people` del anfitrión
  sobre un aviso con código `peace_house_location` (D-82). Sin ese aviso vigente, registrar el
  consentimiento responde 409. Retirarlo deja la casa no publicable y el consentimiento sigue en
  el historial de la persona.
- **Integrantes.**
  - El anfitrión y el contacto entran solos, con `source = role`.
  - Inscribirse indicando una casa (`house_id`) usa `source = enrollment` y solo vale para
    inscripciones activas. Las pendientes de la fase 4 se resolverán ahí.
  - No se puede quitar al anfitrión ni al contacto sin cambiarlos primero.
- **Consolidación.** Se recalcula en cada cambio de integrantes. Si cambia la meta del estado, el
  estatus se actualiza en el siguiente cambio o con el proceso de agregados (fase 3). El detalle
  siempre muestra el avance contra la meta vigente.
- **Cierre:** definitivo, con motivo, como en el diagrama de la ficha. Una casa cerrada no
  admite integrantes ni reuniones.
- **Crédito.**
  - Se calcula al abrir: el primer Embajador activo hacia arriba en la ruta de quien abre
    (incluido él), si no el coordinador de la zona más específica, y si no queda pendiente.
  - Reasignarlo a mano exige un Embajador de Paz activo o un usuario. Cada cambio queda en
    `peace_house_credit_changes` con motivo.
- **Salida de un anfitrión o contacto** (D-92), al dejar el MP o por baja ARCO:
  - termina su participación en las casas;
  - el contacto toma el rol del anfitrión, y viceversa;
  - si no queda nadie, la casa queda con `needs_reassignment`, que se puede filtrar.
- **Reuniones:** los invitados nuevos se crean como personas sin CURP ni domicilio; también se
  aceptan invitados ya registrados.
- **Fotos:** JPEG, PNG o WebP de hasta 10 MB. Se guardan en el almacenamiento S3 (D-94) y se
  leen con URLs firmadas; borrar una foto también borra el objeto.
- **Sin Shapely.** Las coordenadas del punto redondeado se leen del WKB.

*Motivo:* cumplir D-85 y D-92 sin dependencias nuevas, con el consentimiento en el mismo modelo
que los demás avisos.
