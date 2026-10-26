# D-68 · Ciclo de vida de postulaciones y fórmulas

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Fórmulas:** se agregan y editan solo mientras la postulación es borrador y la fórmula está en `aspirant`. Después solo cambian por transición o sustitución.
- **Transiciones:** `aspirant → registered` (captura), `registered → approved` (requiere `nomination.approve`) y `→ cancelled` con motivo (requiere `nomination.approve` salvo en `aspirant`).
- **Sustitución ([D-29](D-29-sustitucion.md)):** requiere `nomination.approve`; debe cambiar al menos a una persona. La fórmula nueva hereda la posición y el estatus de la reemplazada (suposición) y queda ligada por `replaces_formula_id`. Ambas quedan en el historial.
- **Postulación:**
  - **enviar:** exige todas las posiciones esperadas y aplica todas las reglas, incluida la paridad;
  - **aprobar:** requiere `nomination.approve`;
  - **cancelar:** cancela sus fórmulas vigentes y libera la geografía para otra postulación.
- **Creación:**
  - el cargo debe estar habilitado y no ser miembro de planilla en ese proceso;
  - el nodo debe ser del nivel del cargo y pertenecer al marco del proceso y, si es local, a su estado;
  - un municipio con `normative_system` no admite postulaciones de partido (409);
  - RP con `best_loser` espera 0 posiciones ([D-21](D-21-rp-local-configurable.md)).
- **Proceso cerrado:** todo queda de solo lectura (409).
- **Alcance:** las postulaciones nacionales solo las crea y edita un usuario con alcance nacional; con alcance parcial son de solo lectura.
