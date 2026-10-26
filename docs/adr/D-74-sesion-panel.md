# D-74 · Sesión del panel

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Tokens:** el access token se guarda solo en memoria (`lib/auth/session.ts`) y el refresh token sigue en cookie httpOnly ([D-48](D-48-tokens-sesiones.md)). Al recargar, la guarda del layout autenticado renueva con la cookie.
- **401:** el `fetch` del cliente generado renueva una sola vez, con un único refresh en vuelo compartido por las peticiones concurrentes (dos refresh en paralelo parecerían reuso y cerrarían la sesión), y repite la petición. Si la renovación falla, manda al login conservando la ruta.
- **Redirección tras el login:** solo acepta rutas internas, para no abrir redirecciones a otros sitios.
- **Enrolamiento:** los tokens con alcance `mfa_enrollment` solo llegan a `/enroll-mfa`.
