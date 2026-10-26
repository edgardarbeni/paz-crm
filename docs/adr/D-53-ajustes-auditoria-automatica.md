# D-53 · Ajustes a la auditoría automática (detalla [D-45](D-45-implementacion-bitacora.md))

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- `refresh_tokens` y `recovery_codes` no se auditan fila por fila: son secretos de alta rotación. Sus eventos se auditan explícitamente: `login_succeeded`, `login_failed`, `account_locked`, `refresh_reuse_detected`, `logout`, `password_changed`, `password_reset_requested`, `mfa_enrolled`, `mfa_disabled`, `mfa_reset` y `recovery_codes_regenerated`.
- `__audit_ignore_fields__` evita registrar actualizaciones que solo tocan campos de bitácora interna (`user_sessions.last_seen_at`, `ip_address`).
