# D-73 · E2E del panel contra el stack real

- **Estado:** Aceptada
- **Área:** Fase C — geografía

Elección del usuario.
- **Script:** `scripts/e2e.sh` corre igual en local y en CI. Levanta PostGIS y Redis desechables, aplica las migraciones, corre la semilla (`backend/tests/e2e/seed.py`), arranca la API y prueba el build de producción del panel con Playwright.
- **Semilla:** geografía sintética, proceso configurado, personas y postulaciones. Crea un usuario por escenario con secreto TOTP conocido, porque el anti-replay de TOTP y la rotación del refresh token impiden reutilizar una sesión entre tests. Los tests corren en serie.
- **CI:** el job `e2e` reemplaza al Playwright que corría dentro del job `frontend`, y este queda con Biome, `tsc`, Vitest y build.
