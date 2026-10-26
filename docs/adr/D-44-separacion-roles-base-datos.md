# D-44 · Separación de roles de base de datos

- **Estado:** Aceptada
- **Área:** Fase A — implementación

Las migraciones corren con el rol **dueño** (`PAZ_MIGRATIONS_DATABASE_URL`). La API se conecta con un rol de **mínimo privilegio** (`paz_app`), que solo recibe los GRANT que emiten las migraciones:
- DML en los esquemas de módulo;
- en `audit`, solo `SELECT` y `EXECUTE` de `append_entry` / `verify_chain`.

*Motivo:* la inmutabilidad de la bitácora y el principio de mínimo privilegio (ASVS nivel 2).
