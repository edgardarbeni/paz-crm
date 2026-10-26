# D-50 · Contraseñas

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- Argon2id (t=3, m=64 MiB, p=4) con rehash transparente al iniciar sesión.
- Política por longitud (12–128) sin reglas de composición (NIST 800-63B). Rechaza contraseñas repetitivas o que contengan el correo.
- El cotejo contra contraseñas filtradas (ASVS 2.1.7) queda como deuda.
