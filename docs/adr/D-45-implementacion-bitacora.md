# D-45 · Implementación de la bitácora (detalla [D-37](D-37-bitacora-inmutable.md))

- **Estado:** Aceptada
- **Área:** Fase A — implementación
- **Detallada por:** [D-53](D-53-ajustes-auditoria-automatica.md)

- La cadena de hashes se calcula **dentro de PostgreSQL**, en la función `audit.append_entry` (`SECURITY DEFINER`).
- Una fila `audit.chain_head` bloqueada con `FOR UPDATE` serializa los eslabones hasta el commit del llamador.
- Triggers rechazan `UPDATE`, `DELETE` y `TRUNCATE` incluso para el dueño.
- `verify_chain` detecta filas alteradas, huecos y cola truncada.
- Las escrituras del ORM se auditan automáticamente (`AuditedSession`, hook `after_flush`); las sentencias Core no pasan por el hook y deben usar `record_audit`.

*Costo conocido:* el bloqueo es un punto de contención global; se mide en las pruebas de carga de las fases C y D.
