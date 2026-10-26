# D-54 · Ajustes al modelo de identidad (sobre [`reference/data-model.md`](../reference/data-model.md) §2)

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- Columnas nuevas: `roles.grants_all`, `user_sessions.auth_methods` (valores RFC 8176) y `user_invitations.revoked_at`.
- El usuario invitado existe con `status = invited` y sin contraseña hasta aceptar la invitación.
