# D-92 · Reglas de negocio del Movimiento de Paz confirmadas

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz

Respuestas de Darío a las preguntas abiertas y suposiciones de
[peace-movement.md](../modules/peace-movement.md). Reemplazan lo marcado como [SUPUESTO] en esos
puntos.

**Crédito de las casas**
- **Coordinadores por zona** (reemplaza «uno por estado»): un estado puede tener varios
  coordinadores; la zona de cada uno se arma con nodos de cualquier nivel dentro del estado,
  como el alcance de un usuario, y se resuelve a secciones. Si dos zonas cubren la sección de la
  casa, gana la más específica (la de menos secciones). Tienen vigencia con historial.
- **Sin zona:** si no hay Embajador en la cadena ni zona que cubra la sección, la casa queda con
  **crédito pendiente** y aparece en una lista para asignarlo a mano.
- **Se fija al abrir:** ni un ascenso, ni una reasignación de reclutador, ni un cambio de zona lo
  recalculan; solo un coordinator lo reasigna, con motivo.

**Casas**
- **Consolidación reversible:** una casa consolidada que baja de la meta vuelve a `open` y deja de
  contar para la meta del Embajador. La primera fecha de consolidación se conserva.
- **Anfitrión y contacto son integrantes automáticos:** al asignarlos se agregan como integrantes
  y cuentan para el mínimo de 2 y para la meta.
- **Si sale el anfitrión, el contacto toma su rol** (y viceversa). Si no queda ninguno, la casa
  queda marcada para reasignar.
- **Asistentes a reuniones:** pacificadores e invitados. El invitado es una persona de `people`
  (nombre y teléfono opcional, sin CURP ni domicilio); `attendees` guarda `person_id`.

**Inscripción**
- **Importaciones de un coordinator o admin: activas.** Quedan en la bitácora y en el reporte de
  la corrida (precedente de D-33).
- **El reclutador debe estar activo** al inscribir.
- **Rechazo:** la persona creada por una inscripción rechazada se conserva; el rechazo lleva motivo.
- **Consentimiento sin texto aprobado:** el aviso del MP es un dato versionado (código, versión,
  texto y su huella) que carga un admin. Sin un aviso del MP vigente, la inscripción pública
  responde «no disponible» y el panel no deja inscribir. Desarrollo usa un texto de ejemplo
  marcado como tal. El texto definitivo depende de jurídico.

**Configuración** (editable por `admin`, con valores por defecto)
- Semáforo de avance: rojo < 50 %, amarillo 50–99 %, verde ≥ 100 %.
- Umbral de alerta operativa de profundidad: 50 niveles (log y métrica, sin bloquear).

**Baja ARCO:** el nodo anonimizado conserva su estado y su **sección** para que las estadísticas
por geografía sigan cuadrando. Es decisión de negocio; la confirmación jurídica queda pendiente.
