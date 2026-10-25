# Cierre de fase B — Identidad

**Fecha:** 2026-10-24 · **Rama:** `feat/phase-b-identity` · **Estado:** implementada, pendiente de aprobación.

## Criterios de aceptación (PLAN_FASES.md)

| Criterio | Resultado | Evidencia |
|---|---|---|
| Tests de cada flujo de autenticación, incluidos los casos de rechazo | ✅ | `tests/integration/identity/test_login_and_mfa.py`, `test_sessions.py`, `test_passwords_and_invitations.py` |
| TOTP inválido o reusado | ✅ | `test_totp_codes_cannot_be_replayed`, `test_mfa_verify_rejects_bad_input`, unitario `test_totp_window_and_replay` |
| Refresh reusado | ✅ | `test_reusing_a_rotated_token_revokes_the_session` (revoca la sesión completa y se audita) |
| Cuenta bloqueada | ✅ | `test_lockout_after_repeated_failures` |
| Invitación vencida o reusada | ✅ | `test_invitation_lifecycle`, `test_resending_an_invitation_invalidates_the_previous_link` |
| Autorización por permiso, incluido lo que un usuario **no** puede hacer | ✅ | `test_administration.py`: viewer sin acceso, admin no puede escalar a superadmin ni gestionar cuentas superadmin, no se otorgan permisos que no se tienen, último superadmin protegido |
| Cobertura ≥ 85 % en servicios | ✅ | Total **96 %**; servicios de identidad entre 91 y 96 % |
| Flujo real de punta a punta | ✅ | Stack de Compose a través de Caddy: superadmin por CLI, enrolamiento TOTP, invitación recibida en Mailpit y aceptada, login, refresh rotativo, 403 por permiso, logout con revocación inmediata y `paz audit verify-chain` OK |

**Números:**
- **Backend:** 128 tests (68 unitarios + 60 de integración sobre PostgreSQL 18 + PostGIS y Redis reales); cobertura **96 %**; `ruff` y `mypy --strict` sin observaciones.
- **Contrato:** 39 operaciones en OpenAPI; el cliente Hey API se regeneró y el frontend sigue en verde (Biome, `tsc` y Vitest).

## Entregables

| Área | Entregado |
|---|---|
| Modelos y migraciones | `0003`: 11 tablas de `identity`. `0004`: 13 permisos y 5 roles de sistema |
| Autenticación | Login con Argon2id; reto MFA; refresh rotativo con detección de reuso; logout; sesiones por dispositivo (listar, cerrar una, cerrar las demás) |
| 2FA | Enrolamiento TOTP con QR, confirmación, desactivación condicionada, 10 códigos de recuperación, reset administrativo, alcance `mfa_enrollment` |
| Contraseñas e invitaciones | Política por longitud, cambio (cierra las demás sesiones), olvido y restablecimiento, invitaciones con reenvío |
| Defensa | Respuestas genéricas, bloqueo, rate limiting por IP, correo y usuario, verificación de `Origin` en el refresh |
| RBAC | `require_permission` / `permission()`; administración de usuarios, roles y permisos con reglas anti-escalamiento |
| Auditoría | Eventos de seguridad explícitos; visor `GET /api/v1/audit-log` paginado por cursor con filtros |
| Operación | `paz users create-superadmin`; correo SMTP (Mailpit en desarrollo) |
| Core | `app/core/mail.py`, `app/core/rate_limit.py`, errores 401/403/429 con cabeceras, paginación multi-columna, helper `pk()` |
| Documentación | Decisiones D-48 a D-55, `MODELO_DATOS.md` actualizado (D-54), carpetas `auth/` y `admin/` en la colección Bruno, `.env.example` |

## Errores encontrados y corregidos durante la fase

1. **Anti-replay de TOTP anulado en el login (introducido y corregido en esta fase).** Al limpiar código con un reemplazo de texto, la línea que guarda el último paso usado quedó dentro del bloque de error, así que un código TOTP podía usarse dos veces. Lo detectó `test_totp_codes_cannot_be_replayed` antes del commit.
2. **Comparaciones de estado siempre falsas.** La columna `status` es `text` y la base devuelve `str`, así que `is not UserStatus.ACTIVE` siempre era verdadero. Se cambió a `!=`.
3. **Paginación.** Contaba las columnas expandidas de la entidad en lugar de las entidades, y no reconocía el UUID de asyncpg (es una subclase).
4. **Cobertura subestimada.** Faltaba `concurrency = ["thread", "greenlet"]`, porque SQLAlchemy async ejecuta en greenlets. Las cifras de cobertura de la fase A también estaban subestimadas.

## Suposiciones

1. Los 5 roles de sistema solo tienen permisos de identidad y auditoría. Los de candidaturas se agregan en la fase D (coordinator, capturist y viewer hoy no tienen permisos).
2. `admin` puede gestionar todos los usuarios no superadmin. El límite por alcance geográfico llega en la fase C.
3. Los enlaces de los correos apuntan a `PAZ_PUBLIC_BASE_URL` + `/aceptar-invitacion` y `/restablecer-contrasena`; esas pantallas se construyen en la fase E.
4. Un usuario desactivado y luego reactivado vuelve a `active` si ya tenía contraseña, o a `invited` si nunca la definió.

## Deuda técnica

| # | Deuda | Cuándo atenderla |
|---|---|---|
| DT-9 | Falta cotejar contraseñas contra listas de filtradas (ASVS 2.1.7, p. ej. HIBP con k-anonimato) | Antes de producción |
| DT-10 | WebAuthn/passkeys queda solo como extensión de diseño (sin tabla ni endpoints) | Cuando se priorice |
| DT-11 | Con la detección estricta de reuso, dos pestañas refrescando al mismo tiempo pueden cerrar la sesión; el panel debe hacer el refresh de forma serializada | Fase E (cliente) |
| DT-12 | El rate limiting es de ventana fija (permite ráfagas en los bordes) | Si se observa abuso |
| DT-13 | Los permisos se cargan en cada request (2 consultas); no hay caché | Si las métricas lo piden |
| DT-14 | No hay purga de tokens vencidos (invitaciones, reset, refresh) ni de sesiones viejas | Antes de producción (tarea programada) |
| DT-15 | JWT HS256 sin `kid`: rotar `PAZ_JWT_SECRET` invalida todos los access tokens vigentes (se recuperan con refresh) | Al migrar a AWS (KMS / llaves asimétricas) |
| DT-16 | Plantillas de correo básicas (HTML mínimo, sin marca) | Fase E |

## Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-2 | (De la fase A) contención en el bloqueo de la cadena de auditoría; cada login y escritura agrega eslabones | Medir en las pruebas de carga de las fases C y D |
| R-5 | Bloqueo de cuentas como denegación de servicio: alguien que conoce un correo puede bloquearlo 15 min | Desbloqueo automático y desbloqueo por admin; evaluar CAPTCHA o retardo progresivo si ocurre |
| R-6 | Si el reloj del servidor se desfasa, los códigos TOTP fallan | Tolerancia de ±1 paso; el servidor debe tener NTP |
