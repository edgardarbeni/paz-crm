# D-33 · Roles iniciales

- **Estado:** Aceptada
- **Área:** Identidad, acceso y auditoría

Configurables desde el panel. Se precargan:
- `superadmin`: todo, sin alcance.
- `admin`: usuarios y catálogos dentro de su alcance.
- `coordinator`: CRUD de candidaturas en su alcance.
- `capturist`: crea y edita sin aprobar.
- `viewer`: solo lectura.

**TOTP obligatorio** para superadmin, admin y coordinator.
