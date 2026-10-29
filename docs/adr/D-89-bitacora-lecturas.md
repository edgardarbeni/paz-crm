# D-89 · Bitácora de lecturas sensibles (amplía D-37 y D-45)

- **Estado:** Aceptada (2026-10-29: opción B, tabla aparte `audit.access_log`)
- **Área:** Identidad, acceso y auditoría

## Contexto

El MP pide registrar en la bitácora la consulta del detalle de un pacificador, de su red y de
las exportaciones. Hoy solo se auditan escrituras y eventos de sesión.

`audit.audit_log` encadena cada entrada con un candado global (`audit.chain_head ... FOR
UPDATE`, [D-45](D-45-implementacion-bitacora.md)) que se mantiene hasta el commit. Meter cada
lectura ahí serializa las lecturas de todo el sistema detrás de las escrituras, y la meta del
detalle de un nodo es p95 < 200 ms.

## Opciones

**A. Las lecturas en `audit.audit_log`, con la cadena actual.**
- *A favor:* una sola bitácora.
- *En contra:* el candado global entra al camino de lectura; con muchos usuarios es el cuello
  de botella.

**B. Tabla aparte `audit.access_log` (recomendada).**
- Append-only, particionada por mes, con los mismos triggers que rechazan `UPDATE`, `DELETE` y
  `TRUNCATE`; escrita con una función `SECURITY DEFINER`.
- Sin cadena global: una cadena por partición o ninguna (la inmutabilidad la dan los triggers y
  los privilegios).
- Guarda actor, entidad, ID, tipo de lectura, IP y request_id; nunca el contenido leído.
- *A favor:* no compite con las escrituras; se puede retener con otra política.
- *En contra:* dos lugares que consultar; la verificación de integridad es distinta.

## Consecuencia

La consulta de la bitácora (diferencia 3 de `architecture.md`: hoy sin alcance) debe resolverse
para las dos tablas a la vez.
