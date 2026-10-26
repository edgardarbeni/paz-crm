# D-48 · Tokens y sesiones

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- **Access token:** JWT HS256 de 15 min. Viaja en `Authorization: Bearer` y el panel lo guarda solo en memoria. Lleva el id de sesión (`sid`) y el alcance (`scope`).
- **Refresh token:** opaco, de 256 bits, rotativo. Solo se guarda su SHA-256. Viaja en una cookie `paz_refresh` (`HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`) y, como defensa adicional, se verifica el `Origin`.
- **Reuso:** presentar un refresh token ya usado o revocado revoca la sesión completa y se audita como `refresh_reuse_detected`.
- **Duración de la sesión:** 7 días de inactividad máxima y 30 días de vida absoluta.
- **Revocación inmediata:** cada request carga usuario y sesión en una consulta (sesión viva, usuario activo). Esto reemplaza la marca en Redis que mencionaba el plan: es igual de inmediato y no depende de que Redis conserve datos.
- **Reto de MFA:** JWT de 5 min.
- **Alcance `mfa_enrollment`:** si el rol exige 2FA y el usuario no ha enrolado TOTP, solo puede usar los endpoints de enrolamiento, perfil y logout.
