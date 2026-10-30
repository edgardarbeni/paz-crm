# D-104 · Cuentas y acceso originados en nombramientos (amplía D-33, D-35 y D-52)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Identidad, acceso y auditoría · Estructura del partido

Reglas para que un nombramiento con `grants_access` produzca una concesión
([D-101](D-101-concesiones-rol-alcance.md)).

1. **Cuenta ↔ persona sin FK desde el núcleo.** El vínculo vive en el módulo:
   `party_structure.person_accounts (person_id, user_id)`, único en ambos lados. `identity` no
   depende de `people` ni de la estructura. *(Alternativa descartada: `identity.users.person_id`,
   que hace que el núcleo dependa de un módulo, el problema que resolvió la opción B de
   [D-83](D-83-alcance-por-rama.md).)*
2. **Alta por invitación ([D-35](D-35-alta-usuarios-correo.md)).** Dar acceso crea la cuenta
   `invited` y envía la invitación, o reutiliza la cuenta de la persona si ya existe.
3. **TOTP pegajoso.** Nueva columna `identity.users.mfa_required`, que se activa al originarse
   una concesión en un cargo y no se desactiva sola. La exigencia es `mfa_required` o algún rol
   con `requires_mfa`. Así se cumple el [SUPUESTO] de la ficha.
4. **Al terminar un nombramiento** se retira su concesión. Las sesiones **solo** se revocan si la
   cuenta se queda sin concesiones. La autorización se verifica en la base de datos en cada
   petición, así que el permiso desaparece en la siguiente petición, y cerrar la sesión le
   quitaría también sus otros cargos.
5. **Antiescalamiento al nombrar ([D-52](D-52-reglas-rbac.md)).** Si quien nombra no puede conceder
   el rol y el alcance del cargo, el nombramiento se registra **sin acceso** y se avisa que lo debe
   otorgar alguien con `party_structure.appointment.grant_access` y el alcance suficiente. El
   nombramiento no se bloquea: registrar quién ocupa el cargo no da poder.
6. **Roles base de la estructura ([D-33](D-33-roles-iniciales.md)).** Se agregan roles nuevos con
   `requires_mfa`. No se reutiliza `coordinator`, que en D-33 significa candidaturas. Sus nombres y
   permisos están pendientes (pregunta abierta 4 de la ficha). «Admin nacional» en la ficha
   significa `admin` con alcance nacional, no `superadmin`.

*Motivo:* acceso por cargo sin acoplar el núcleo a los módulos y sin quitarle al titular más de lo
que perdió.
