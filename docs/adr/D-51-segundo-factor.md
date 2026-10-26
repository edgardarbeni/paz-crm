# D-51 · Segundo factor

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- **TOTP:** RFC 6238 (SHA-1, 6 dígitos, 30 s, tolerancia de ±1 paso) con anti-replay por paso (`last_used_step`). El secreto, de 160 bits, se cifra con `FieldCipher` (contexto `identity.totp_credentials.secret`).
- **QR:** se genera en el backend como data URI SVG.
- **Códigos de recuperación:** 10 de un solo uso, de 80 bits, guardados con HMAC (no Argon2: su entropía lo permite y verificarlos sale barato).
- **Desactivar TOTP** requiere contraseña + código y no se permite si el rol exige 2FA.
- **Reset administrativo:** borra el TOTP y cierra las sesiones del usuario.
