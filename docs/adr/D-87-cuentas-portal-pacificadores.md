# D-87 · Cuentas del portal de pacificadores

- **Estado:** Propuesta (entrega posterior; puede decidirse más adelante)
- **Área:** Movimiento de Paz · Identidad, acceso y auditoría

## Contexto

El portal de pacificadores (entrega posterior) usa correo y contraseña, sin TOTP obligatorio,
separado del panel. Sus endpoints `/me/...` se limitan a la red propia y nunca reutilizan los
permisos del panel.

## Opciones

**A. Usuarios de `identity` con `account_type = member` y audiencia de token `portal` (recomendada).**
- Reutiliza Argon2, sesiones, revocación inmediata y defensa del login (D-48 a D-50).
- Las dependencias del panel rechazan tokens con audiencia `portal`, y las del portal, los del
  panel.
- *A favor:* el código de seguridad ya probado no se duplica; una sola bitácora de accesos.
- *En contra:* `identity.users` mezcla dos poblaciones; hay que cuidar que ningún listado o
  permiso del panel las incluya.

**B. Dominio de autenticación aparte (`peace_movement.portal_accounts`).**
- *A favor:* aislamiento total.
- *En contra:* duplica hash de contraseñas, sesiones, recuperación y límites de intentos.
