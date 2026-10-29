# D-93 · Bitácora: alcance de consulta, enmascarado de personas y escrituras Core (detalla D-37 y D-45)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Identidad, acceso y auditoría

Resuelve las diferencias 1, 3 y 10 de `architecture.md` §8 (fase 0a del Movimiento de Paz).

- **Alcance de consulta (diferencia 3).** Las entradas son genéricas, así que el alcance se
  resuelve por **actor**, no por entidad. Un usuario con alcance limitado ve en
  `GET /audit-log` y `GET /audit-log/access` las entradas hechas por él mismo o por usuarios que
  puede gestionar (alcance dentro del suyo, la regla de `manageable_users_filter`). Las entradas
  sin actor (cron, CLI) y las de superadministradores solo las ve quien no tiene restricción.
- **Enmascarado de personas (diferencia 10).** `Person` declara `__audit_masked__` para nombre,
  apellidos, `search_name`, fecha de nacimiento, sexo y entidad de nacimiento; `PersonAddress`,
  para el código postal. La bitácora registra que hubo un cambio y en qué campos, pero no el
  valor, porque es inmutable y la purga ARCO ([D-69](D-69-baja-personas-suposicion-confirmar.md))
  no puede borrarla. La geografía del domicilio se conserva, como el nodo anonimizado del MP
  ([D-92](D-92-reglas-negocio-movimiento-paz.md)).
- **Escrituras Core (diferencia 1).** Las cuatro escrituras que se saltaban el hook pasan al
  ORM: el reemplazo de alcances (`set_scopes`), de contactos y domicilios (`update_person`), de
  integrantes de fórmula (`update_members`) y los borrados de la purga (`purge_due`). Son pocas
  filas por operación, así que no ameritan una entrada por lote
  ([D-90](D-90-auditoria-escrituras-masivas.md), `record_bulk`, queda para las escrituras
  masivas del MP).
- **Lecturas sensibles.** El detalle de una persona (`GET /people/{id}`) queda en
  `audit.access_log` ([D-89](D-89-bitacora-lecturas.md)) con `details.unmasked`, que indica si
  la respuesta llevaba los datos sin enmascarar. Las búsquedas no se registran todavía.

*Motivo:* un admin estatal no debe leer el antes y el después de registros de otros estados, y
la bitácora inmutable no debe guardar datos que un titular puede pedir borrar. (Descartadas para
el alcance: solo usuarios sin restricción, porque deja sin bitácora a los admins estatales; y
resolver el alcance por entidad, porque las entradas de tablas sin geografía no tendrían regla.)
