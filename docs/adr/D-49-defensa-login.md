# D-49 · Defensa del login

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- **Respuesta única:** todo fallo devuelve el mismo 401 genérico; el motivo solo queda en la bitácora (`login_failed`). Cuando la cuenta no existe se verifica un hash ficticio, para que el tiempo de respuesta no lo delate.
- **Bloqueo:** 5 intentos fallidos (contraseña, TOTP o código de recuperación) bloquean la cuenta 15 min.
- **Rate limiting** (ventana fija en Redis):

  | Endpoint | Límite |
  |---|---|
  | Login, por IP | 20/min |
  | Login, por correo | 10/15 min |
  | MFA, por usuario | 5/5 min |
  | Restablecer contraseña, por correo | 5/h |

- **Sin enumeración:** `password/forgot` siempre responde 202.
