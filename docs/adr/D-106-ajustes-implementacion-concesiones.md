# D-106 · Ajustes de implementación de las concesiones (fase 0 de la estructura; detalla D-101)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Identidad, acceso y auditoría · Estructura del partido

Cómo quedó implementada [D-101](D-101-concesiones-rol-alcance.md) (migración `0018`).

**Modelo y migración**
- Las tablas `identity.user_grants`, `user_grant_scopes` y `user_grant_sections` reemplazan a
  `user_roles`, `user_scopes` y `user_scope_sections`.
- Cada (usuario, rol) vigente pasó a una concesión manual con todos los alcances del usuario, así
  que el acceso de cada quien no cambió.
- La reversa de la migración reconstruye la unión por usuario. Pierde la separación por
  concesión, que el modelo anterior no puede representar.
- `peace_movement.user_branch_scopes` cambia `user_id` por `grant_id`. Cada rama existente se
  copió a cada concesión del usuario cuyo rol tiene permisos del MP; las ramas de usuarios sin
  esos permisos no daban acceso y se descartaron.

**Alcance por permiso**
- `permission(Perm.X)` entrega `CurrentUser.geo` acotado a las concesiones que incluyen X. Las
  rutas sin permiso (la cuenta propia) reciben todas.
- Los módulos ya no leen la tabla derivada: usan `GeoScope.sections_filter`, `section_sql` y
  `sql_params` (geografía, candidaturas, personas, MP y bitácora).
- Las importaciones del MP se procesan con el alcance de `peace_movement.member.import`.

**Permisos secundarios (decisión conservadora).** Desenmascarar (`read_sensitive`), aprobar y
forzar reglas de candidaturas aplican solo si su alcance **cubre todo** el alcance del permiso
de la ruta (`CurrentUser.holds_within`). Si lo cubre solo en parte, no aplican en ninguna parte
de esa consulta.
- *Motivo:* evita la fuga sin calcular el permiso registro por registro.
- *Costo:* quien desenmascara en un estado y consulta en dos verá los datos enmascarados en
  ambos. Si se vuelve un problema, se calcula por registro.

**API**
- `GET` y `PUT /users/{id}/grants` reemplazan a `PUT /users/{id}/roles` y a
  `GET`/`PUT /users/{id}/scopes`. El `PUT` exige `identity.user.assign_roles` y
  `identity.user.assign_scopes`.
  - Reemplaza solo las concesiones manuales. Una concesión se conserva mandando su `id`.
  - El rol de una concesión no cambia: se quita y se agrega otra.
  - Una concesión que combina el alcance nacional con otros nodos responde 400.
- Quitar, cambiar o agregar una concesión exige poder concederla: el rol completo, en ese
  alcance, para cada permiso.
- `GET /auth/me` devuelve `grants` en lugar de `geo_scopes`. `UserOut.roles` sigue siendo la
  lista de roles distintos.
- Invitar con roles crea concesiones sin alcance: no ven nada hasta que se les asigne uno.
- Las ramas se gestionan en `GET`/`PUT /peace-movement/grants/{id}/branches`. Para otorgar una
  rama, el actor debe tener los permisos del MP del rol de la concesión (la rama solo amplía
  esos) y la rama debe estar dentro de una que él ya tiene (D-83).

**Bitácora**
- Concesiones y alcances se crean y se borran con el ORM, así que quedan en la bitácora.
- Borrar una concesión borra sus ramas por la FK en cascada. Esas filas no tienen entrada
  propia, pero la concesión borrada sí.

**Otros**
- El informe de `paz geo activate` cuenta `grants_rebuilt` en lugar de `users_rebuilt`.
- En el panel, la ficha del usuario muestra «Concesiones (rol y alcance)»: cada concesión con
  su origen, su alcance editable si es manual y sus ramas del MP.
