# D-55 · Correo y arranque

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- **Correo:** el backend puede ser `smtp`, `console` o `memory`. Los correos salen en segundo plano después del commit. Los enlaces apuntan a rutas del panel que se construyen en la fase E (`/aceptar-invitacion`, `/restablecer-contrasena`).
- **Primer superadmin:** se crea con `paz users create-superadmin` y debe enrolar TOTP en su primer acceso.
