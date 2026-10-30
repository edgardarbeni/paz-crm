# D-109 · Acceso al sistema por nombramiento (fase 3 de la estructura; detalla D-104)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Estructura del partido · Identidad, acceso y auditoría

Cómo quedó implementada [D-104](D-104-cuentas-acceso-por-nombramiento.md) (migración `0021`).

**Cuenta de la persona**
- `party_structure.person_accounts` liga una persona con una cuenta: a lo más una de cada lado.
- Al dar acceso:
  - si la persona ya tiene cuenta, se reutiliza;
  - si no, se usa el correo indicado. Si ya existe un usuario con ese correo y no está ligado a
    otra persona, se liga; si está ligado a otra persona, responde 409;
  - si el correo no existe, se crea la cuenta `invited` y se envía la invitación de siempre
    (D-35, 72 h).

**Concesión del nombramiento**
- Cada nombramiento con acceso crea **una** concesión con origen `appointment`, `source_id` igual
  al nombramiento y el rol del nombramiento (por defecto, el del cargo).
- Su alcance es el territorio del asiento:
  - nacional para los cargos nacionales;
  - la circunscripción para las Secretarías de Circunscripción;
  - el estado para los órganos estatales;
  - el distrito o municipio para los comités.
- Esa concesión no se toca desde `PUT /users/{id}/grants`: sigue al nombramiento.
- **Antiescalamiento:** quien da el acceso necesita `party_structure.appointment.grant_access`,
  administrar el asiento (nivel y alcance, D-108) y poder conceder ese rol en ese territorio
  (D-101).
- Si se pide acceso al nombrar y no se puede dar, el nombramiento se registra igual y
  `access_pending` dice por qué (D-104 punto 5).
  - `POST /appointments/{id}/access` lo da después.
  - `DELETE` lo quita y el cargo sigue vigente.

**TOTP obligatorio:** dar acceso marca `users.mfa_required`, que no se desactiva solo.
`Access.requires_mfa` lo toma en cuenta, así que el primer ingreso exige configurar el TOTP.

**Revocación**
- Terminar un nombramiento, a mano o por vencimiento, borra su concesión.
- Las sesiones se cierran **solo** si la cuenta se queda sin concesiones. Los permisos ya se
  verifican en la base de datos en cada petición.
- La cuenta sigue ligada a la persona para el siguiente cargo.

**Tarea diaria:** `paz party-structure expire` corre a las 03:50 en el `scheduler` con candado
consultivo. Termina como `term_end` en su `ends_on` los nombramientos vencidos y retira su acceso.

**Ajuste en `identity`:** `Access` guarda una copia inmutable de cada rol (`RoleInfo`) en lugar
de la fila ORM. Así sobrevive a un rollback dentro de la misma petición; antes fallaba al dar un
acceso rechazado.
