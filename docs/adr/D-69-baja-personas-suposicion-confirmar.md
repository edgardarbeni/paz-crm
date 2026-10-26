# D-69 · Baja de personas (ARCO) — suposición a confirmar

- **Estado:** Aceptada
- **Área:** Fase C — geografía

`DELETE /people/{id}` hace soft-delete y fija `purge_after = hoy + 30 días`. `paz people purge`, programable con cron, anonimiza después: borra contactos, domicilios y consentimientos, y deja el nombre como `[eliminado]` y sin CURP. La fila se conserva para no romper el historial de candidaturas. No se puede dar de baja a quien integra una fórmula vigente. **El plazo de 30 días es una suposición** (`PURGE_RETENTION_DAYS`), pendiente de la política de privacidad del partido.
