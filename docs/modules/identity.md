# Módulo: Identidad y acceso

## Propósito y usuarios

Controla quién entra a PAZOS, qué puede hacer y sobre qué parte del país. También expone la
consulta de la bitácora de auditoría.

| Usuario | Qué resuelve aquí |
|---|---|
| Superadmin | Arranque del sistema, gestión de cuentas superadmin y de roles |
| Admin | Invita, edita, desactiva y desbloquea usuarios; asigna roles y alcances dentro de su alcance; consulta la bitácora |
| Cualquier usuario | Inicia sesión, enrola TOTP, cambia o restablece su contraseña, administra sus sesiones (`/account`) |
| Otros módulos | Reciben `CurrentUser` con permisos y alcance para autorizar cada petición |

Código: `backend/app/modules/identity/` y `backend/app/modules/audit/router.py`. Pantallas
del panel: `/users`, `/roles`, `/audit`, `/account`, `/login`, `/enroll-mfa`,
`/aceptar-invitacion` y `/restablecer-contrasena`.

## Dependencias

- **Núcleo** ([`architecture.md`](../architecture.md)):
  - `core/crypto` (`FieldCipher` para el secreto TOTP, `BlindIndexer` para los códigos de recuperación);
  - `core/rate_limit` (Redis);
  - `core/mail` (SMTP; Mailpit en desarrollo);
  - `core/audit` (bitácora, §5);
  - `core/pagination` y `core/errors`.
- **Geografía:** `user_scopes` y `user_scope_sections` referencian los nodos de `geography`
  del marco activo. Al activar un marco, `paz geo activate` remapea los alcances y llama a
  `scopes.rebuild_all` ([`geography.md`](geography.md)).

## Entidades y relaciones

ER completo: [`reference/data-model.md` §2](../reference/data-model.md#2-identidad-identity)
y §5 (auditoría). Migraciones `0003` (tablas), `0004` (roles y permisos) y `0006` (alcances).

| Tabla | Claves y notas |
|---|---|
| `users` | `email` citext único, `password_hash` Argon2id, `status` `invited \| active \| locked \| disabled`, contador de fallos y `locked_until` |
| `user_invitations` | `token_hash` único, vence en 72 h (`invitation_ttl_seconds`), `accepted_at`, `revoked_at` ([D-54](../adr/D-54-ajustes-modelo-identidad.md)) |
| `password_reset_tokens` | `token_hash` único, vence en 30 min |
| `totp_credentials` | Uno por usuario; `secret_ciphertext` + `key_version`; `last_used_step` (anti-replay); `confirmed_at` |
| `recovery_codes` | 10 por usuario, `code_hash` HMAC, `used_at` |
| `user_sessions` | Una por dispositivo: `user_agent`, `ip_address`, `auth_methods` (RFC 8176), `expires_at`, `revoked_at`, `revoke_reason` |
| `refresh_tokens` | `token_hash` único, `parent_token_id` para detectar reuso |
| `roles` | `code` único, `requires_mfa`, `is_system`, `grants_all` |
| `permissions` | `code` único `<módulo>.<recurso>.<acción>`; sembrados por migración |
| `role_permissions`, `user_roles` | Tablas puente N:M |
| `user_scopes` | `scope_level` (`national`, `electoral_region`, `state`, `federal_district`, `local_district`, `municipality`, `section`) con una FK nullable por nivel y `CHECK` de exclusividad |
| `user_scope_sections` | Derivada `(user_id, section_id)`; se reconstruye, no se edita |
| `audit.audit_log` | Append-only con cadena de hashes; se lee aquí ([architecture §5](../architecture.md#5-auditoría-d-37-d-45-d-53)) |

**Ciclo de vida del usuario** ([D-35](../adr/D-35-alta-usuarios-correo.md), [D-54](../adr/D-54-ajustes-modelo-identidad.md)):
- `invited` (sin contraseña) → `active` al aceptar la invitación.
- `active` → `locked` tras 5 fallos; vuelve a `active` en 15 min o por desbloqueo de un admin.
- `active` ↔ `disabled` por un admin. Al reactivar vuelve a `active` si ya tenía contraseña, o
  a `invited` si nunca la definió (suposición de FASE_B).

**Sesión** ([D-48](../adr/D-48-tokens-sesiones.md)):
- El access token es un JWT HS256 de 15 min.
- El refresh token es opaco y rotativo, y viaja en la cookie `paz_refresh`.
- La sesión dura 7 días de inactividad y 30 de vida absoluta.
- El reto MFA es un JWT de 5 min.

## Reglas de negocio

**Autenticación:**
- **Login:** correo y contraseña, Argon2id con t=3, m=64 MiB, p=4 y rehash transparente
  ([D-50](../adr/D-50-contrasenas.md)).
- **Respuesta única:** cualquier fallo devuelve el mismo 401 y se verifica un hash ficticio
  si la cuenta no existe ([D-49](../adr/D-49-defensa-login.md)).
- **Bloqueo:** 5 intentos fallidos (contraseña, TOTP o código de recuperación) bloquean la
  cuenta 15 min (`max_failed_logins`, `lockout_seconds`).
- **Rate limiting** (ventana fija en Redis):

  | Endpoint | Límite |
  |---|---|
  | Login, por IP | 20/min |
  | Login, por correo | 10/15 min |
  | MFA, por usuario | 5/5 min |
  | Restablecer contraseña, por correo | 5/h |

- `password/forgot` siempre responde 202.

**Contraseñas:**
- Entre 12 y 128 caracteres, sin reglas de composición.
- Se rechazan las repetitivas y las que contienen el correo.
- Cambiarla cierra las demás sesiones.

**Segundo factor** ([D-51](../adr/D-51-segundo-factor.md)):
- **TOTP:** RFC 6238 (SHA-1, 6 dígitos, 30 s, ±1 paso), compatible con Google Authenticator, Microsoft Authenticator y 1Password.
  - El QR se genera en el backend.
  - Cada código sirve una sola vez por paso.
- **Obligatorio** si algún rol del usuario tiene `requires_mfa`. Mientras no lo enrole, su
  token tiene alcance `mfa_enrollment` y solo llega a los endpoints de enrolamiento, perfil y
  logout.
- **Códigos de recuperación:** 10, de un solo uso.
- **Desactivar TOTP** requiere contraseña y código, y no se permite si el rol lo exige.
- **Reset administrativo:** borra el TOTP y cierra las sesiones del usuario.

**Sesiones:**
- Al presentar un refresh token ya usado o revocado se revoca la sesión completa
  (`refresh_reuse_detected`).
- El refresh exige además un `Origin` permitido.
- Cada usuario lista y cierra sus sesiones, una por una o todas las demás.
- Un admin puede cerrar todas las sesiones de otro usuario.
- La revocación es inmediata: cada petición verifica la sesión en la base de datos.

**Altas:**
- Solo por invitación de un admin; no hay registro público.
- Reenviar una invitación invalida el enlace anterior y solo aplica a usuarios `invited`.
- El primer superadmin se crea con `paz users create-superadmin` ([D-55](../adr/D-55-correo-arranque.md)).

**RBAC** ([D-52](../adr/D-52-reglas-rbac.md)):
- `grants_all` concede todos los permisos.
- Nadie asigna roles ni otorga permisos que no tiene (`ensure_can_assign`, `ensure_can_grant`).
- Solo un superadmin gestiona cuentas superadmin, y el último superadmin no se puede desactivar ni degradar.
- Los roles de sistema no se eliminan, `superadmin` es inmutable y un rol con usuarios no se elimina.

**Alcance** ([D-34](../adr/D-34-alcance-geografico.md)):
- `PUT /users/{id}/scopes` reemplaza los alcances y valida que cada nodo exista en el marco activo.
- No se puede otorgar un nodo con secciones fuera del alcance propio.
- El alcance nacional solo lo otorga quien ya lo tiene.

## Permisos y alcance

**Roles de sistema** ([D-33](../adr/D-33-roles-iniciales.md); se pueden crear más desde `/roles`):

| Rol | TOTP | Permisos sembrados |
|---|---|---|
| `superadmin` | Sí | Todos (`grants_all`), sin restricción geográfica |
| `admin` | Sí | `identity.*` salvo `role.create`, `role.update` y `role.delete`; `audit.log.read`; geografía; personas y catálogos de candidaturas (migraciones 0006 y 0008) |
| `coordinator` | Sí | Candidaturas y personas (0006 y 0008) |
| `capturist` | No | Captura sin aprobar |
| `viewer` | No | Solo lectura |

**Permisos del módulo** (`identity/permissions.py:Perm`):

| Código | Acción |
|---|---|
| `identity.user.read`, `.create`, `.update`, `.disable` | Usuarios |
| `identity.user.assign_roles`, `.assign_scopes` | Roles y alcances de un usuario |
| `identity.user.reset_mfa`, `.revoke_sessions` | Seguridad de una cuenta |
| `identity.role.read`, `.create`, `.update`, `.delete` | Roles |
| `identity.permission.read` | Catálogo de permisos |
| `audit.log.read` | Bitácora |

`Perm` es el registro único de permisos de **todos** los módulos. Los permisos se siembran
por migración, y un test exige que la base y el código coincidan. El panel tiene una copia
manual en `frontend/src/lib/auth/permissions.ts`.

**Alcance geográfico:**
- Un usuario se gestiona solo si su alcance está dentro del del actor o si aún no tiene
  alcance (`manageable_users_filter`, `ensure_within_scope`). El filtro se aplica en la
  consulta SQL.
- Sin alcance no se ve nada; superadmin y alcance nacional no tienen restricción.

## Datos sensibles

| Dato | Protección | En la bitácora |
|---|---|---|
| Contraseña | Argon2id | `password_hash` sale como `***` (`__audit_masked__`) |
| Secreto TOTP | `FieldCipher`, contexto `identity.totp_credentials.secret` | `bytes`: siempre enmascarado |
| Códigos de recuperación | HMAC | No se auditan por fila (`__audit__ = False`); `recovery_codes_regenerated` es explícito ([D-53](../adr/D-53-ajustes-auditoria-automatica.md)) |
| Refresh, invitación, reset | Solo se guarda el SHA-256 | Refresh no se audita por fila (D-53) |

**Eventos auditados explícitamente:** `login_succeeded`, `login_failed` (con el motivo),
`account_locked`, `refresh_reuse_detected`, `logout`, `password_changed`,
`password_reset_requested`, `mfa_enrolled`, `mfa_disabled`, `mfa_reset` y
`recovery_codes_regenerated`. `user_sessions` ignora los cambios que solo tocan
`last_seen_at` o `ip_address`.

**Auditoría de lectura:** no existe. Las consultas no se registran en la bitácora (pendiente
de definir si se requiere).

## Volumen y rendimiento

- **Por petición:** una consulta de usuario más sesión, dos de permisos y una de alcance. No
  hay caché de permisos (DT-13).
- **Alcances:** en el benchmark nacional de la fase C, `user_scope_sections` recibió 5,589
  filas para un usuario acotado. Sin `ANALYZE`, una tesela tardó 207 ms; analizada, 5.6 ms.
  Por eso se ejecuta `ANALYZE` tras las reconstrucciones masivas
  ([D-63](../adr/D-63-operacion-geografia.md), riesgo R-7).
- **Volumen de usuarios, sesiones y bitácora:** sin medición.
- **Cadena de la bitácora:** es un punto de contención global (R-2), sin medición bajo carga.

## Integraciones y eventos

**Consumen otros módulos:**
- `CurrentUserDep`, `AnyScopeUserDep` y `permission(Perm.X)` (`identity/dependencies.py`).
- `CurrentUser.geo` (`GeoScope`), con `sections_filter(col)` para filtrar por alcance.
- `ServicesDep` (`identity/container.py`): tokens, `cipher`, `indexer`, rate limiter y
  correo. `people` lo usa para cifrar.
- `record_audit` y la sesión auditada (núcleo), con los que este módulo emite los eventos de
  seguridad.

**Consume este módulo:**
- La geografía del marco activo, para validar nodos de alcance.
- `paz geo activate`, que remapea los alcances y reconstruye `user_scope_sections`.

**Correo saliente** (después del commit): invitaciones y restablecimiento de contraseña, con
enlaces a `PAZ_PUBLIC_BASE_URL`.

**Panel:** `/auth/me` entrega roles y permisos efectivos. El access token vive en memoria y
el panel hace un solo refresh en vuelo ([D-74](../adr/D-74-sesion-panel.md)).

## Criterios de aceptación

Cubiertos por `tests/integration/identity/` y `tests/integration/geography/`:

- [x] Login correcto emite access token y cookie `HttpOnly; Secure; SameSite=Strict` (`test_login_issues_tokens_and_secure_cookie`).
- [x] Los fallos no se distinguen entre sí; 5 fallos bloquean la cuenta; hay rate limit por correo.
- [x] Un rol con `requires_mfa` obliga a enrolar TOTP; un código TOTP no se reutiliza; los códigos de recuperación son de un solo uso.
- [x] El refresh rota el token; reusar uno revoca la sesión; sin cookie u `Origin` válido se rechaza.
- [x] El logout invalida access y refresh al instante; una sesión expirada se rechaza; nadie cierra sesiones ajenas.
- [x] Una invitación vencida o reusada se rechaza, y reenviarla invalida el enlace anterior. El flujo de restablecimiento funciona, y cambiar la contraseña conserva solo la sesión actual.
- [x] El viewer no llega a la administración; el admin no escala a superadmin ni gestiona cuentas superadmin; nadie otorga permisos que no tiene; el último superadmin está protegido.
- [x] El catálogo de permisos de la base coincide con `Perm` (`test_migrations_seed_the_registry`, `test_permission_catalog_matches_code_registry`).
- [x] Sin alcance no se ve nada; un usuario no otorga alcance fuera del suyo; la administración de usuarios se limita por alcance; el alcance nacional ve todo.
- [x] La bitácora se consulta con filtros y cursor (`test_audit_log_viewer`).
- [ ] **Quitar un alcance queda en la bitácora.** Hoy no: `set_scopes` borra los `user_scopes` anteriores con una sentencia Core (`services/scopes.py:214`), sin `record_audit` ([architecture §8](../architecture.md#8-diferencias-entre-el-código-y-claudemd)).
- [ ] **Bitácora limitada por alcance.** Hoy un admin estatal lee la bitácora completa (`GET /audit-log` solo exige `audit.log.read`). Pendiente de definir si es intencional.
- [ ] **Contraseñas filtradas** (ASVS 2.1.7): se rechazan. Pendiente (DT-9).

## Fuera de alcance

- **WebAuthn/passkeys:** solo previsto como extensión. Una tabla `webauthn_credentials`
  futura no toca las existentes, y `auth_methods` ya admite métodos nuevos (DT-10).
- **Registro público y SSO** con proveedores externos ([D-35](../adr/D-35-alta-usuarios-correo.md)).
- **Purga programada** de tokens vencidos y sesiones viejas (DT-14, antes de producción).
- **Llaves asimétricas o `kid` en el JWT;** rotar `PAZ_JWT_SECRET` invalida los access
  tokens vigentes (DT-15).
- **CAPTCHA o retardo progresivo** contra el bloqueo malicioso de cuentas (R-5, solo si
  ocurre).
- **Rate limiting de ventana deslizante** (DT-12).
