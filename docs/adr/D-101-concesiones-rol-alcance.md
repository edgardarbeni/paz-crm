# D-101 · Concesiones (rol, alcance) (reemplaza D-34 en el modelo del alcance; amplía D-52 y D-83)

- **Estado:** Propuesta (2026-10-30)
- **Área:** Identidad, acceso y auditoría · Estructura del partido

## Contexto

La ficha [party-structure.md](../modules/party-structure.md) permite que una persona ocupe varios
cargos, cada uno con su rol y su territorio. Hoy el acceso no puede representarlo:

- Los permisos son la unión de los roles del usuario (`identity/services/access.py:load_access`).
- El alcance es uno por usuario: `identity.user_scopes` se resuelve a `user_scope_sections` y llega
  a cada servicio como un único `CurrentUser.geo` ([D-34](D-34-alcance-geografico.md)).

Con dos cargos, la combinación filtra permisos. La Directora Jurídica de Baja California que además
coordina secciones en Sonora tendría permisos jurídicos en Sonora. Las ramas del Movimiento de Paz
([D-83](D-83-alcance-por-rama.md), `peace_movement.user_branch_scopes`) tienen la misma fuga dentro
del MP: una rama habilita todos los permisos del MP que el usuario tenga por cualquier rol.

## Opciones

**A. Concesiones con alcance por permiso (recomendada).**
- Tablas en `identity`:
  - `user_grants`: `user_id`, `role_id`, `origin` (`manual` o `appointment`), `source_id`
    (el nombramiento que la originó, sin FK hacia el módulo de estructura), vigencia;
  - `user_grant_scopes`: los nodos de cada concesión, con las mismas columnas y restricción de
    nivel que hoy tiene `user_scopes`;
  - `user_grant_sections`: tabla derivada `(grant_id, section_id)`; reemplaza a
    `user_scope_sections`. El alcance nacional no se materializa.
- Al autenticar se cargan las concesiones vigentes con sus permisos. `permission(Perm.X)` entrega
  un `CurrentUser` cuyo `geo` ya está acotado a las concesiones que incluyen X;
  `GeoScope.sections_filter` filtra con `EXISTS … grant_id = ANY(:grants)`. «Sin restricción» se
  evalúa también por permiso: superadmin o alguna concesión nacional que incluya X.
- Cuando un servicio usa un segundo permiso (por ejemplo `people.person.read_sensitive` o
  `peace_movement.house.reassign_credit`), pide el alcance de ese permiso con
  `current.geo_for(Perm.Y)`.
- *A favor:* el acceso es la suma de los cargos, sin fugas. La mayoría de los usos de
  `user.geo` (82 en 13 archivos) no cambian, porque el `geo` llega ya acotado.
- *En contra:* es el cambio más delicado del núcleo; hay que revisar los 22 `.has()` de los
  servicios.

**B. Un cargo activo por sesión.**
- El usuario elige con qué concesión opera y la sesión guarda `active_grant_id`. Permisos y alcance
  son solo los de esa concesión.
- *A favor:* el código casi no cambia y es muy difícil que filtre.
- *En contra:* contradice la ficha («su acceso es la suma»). Quien tiene dos cargos alterna entre
  ellos y no ve los dos territorios a la vez.

## Reglas comunes a ambas opciones

- **Migración:** cada usuario actual queda con una concesión manual por rol, y cada una lleva todos
  sus alcances actuales. El acceso de hoy se conserva exacto.
- **Antiescalamiento ([D-52](D-52-reglas-rbac.md)):** se concede (R, S) solo si el actor tiene cada
  permiso de R y, para cada uno, S está dentro del alcance que el actor tiene para ese permiso. El
  alcance nacional de un permiso solo lo concede quien ya lo tiene para ese permiso.
- **TOTP:** se exige si el rol de alguna concesión vigente tiene `requires_mfa` (ver
  [D-104](D-104-cuentas-acceso-por-nombramiento.md) para cuentas originadas en cargos).
- **Ramas del MP ([D-83](D-83-alcance-por-rama.md)):** una rama deja de ser un alcance suelto del
  usuario y pasa a ser el alcance de una concesión de un rol del MP. Sigue viviendo en el módulo
  (`peace_movement.user_branch_scopes` gana `grant_id`), así que el núcleo no depende del MP.
- **Gestión de usuarios y bitácora:** `manageable_users_filter`, `ensure_within_scope` y el alcance
  de la bitácora ([D-93](D-93-bitacora-alcance-y-enmascarado.md)) usan el alcance del permiso
  `identity.user.*` correspondiente.
- **Marco geográfico:** `paz geo activate` remapea `user_grant_scopes` como hoy remapea
  `user_scopes` (ver [D-102](D-102-cambio-marco-estructura.md)).
- **Bitácora:** crear, cambiar o retirar una concesión pasa por el ORM y registra su origen.

## Impacto en el código existente (opción A)

| Área | Cambio |
|---|---|
| `identity` | Modelos y migración; `load_access`, `resolve_scope`, `CurrentUser`, `require_permission`; `set_scopes` pasa a gestionar concesiones; `rebuild_all`, `ensure_can_assign`, `ensure_can_grant`, `manageable_users_filter`, `ensure_within_scope` |
| `geography` | `frameworks.py` remapea `user_grant_scopes` |
| `audit` | Alcance de «usuarios que gestiona» |
| `people` | Enmascarado con el alcance de `read_sensitive` |
| `candidacies` | `is_editable` con el alcance del permiso de escritura |
| `peace_movement` | `scope.py` y ramas por concesión |
| Panel | La ficha de usuario muestra una lista de concesiones (rol y alcance) en lugar de roles y alcances por separado (`users/$userId.tsx`, `scopes-editor.tsx`) |
| Pruebas | Suites de alcance (unas 6) y pruebas nuevas de fuga entre concesiones |

*Motivo:* es el único modelo que cumple la ficha sin fugas y sin obligar a cambiar de cargo.
