"""Login, second factor and logout.

Every failure answers with the same generic message, so responses do not reveal whether an
account exists, is locked or has a wrong password (the reason is only in the audit log).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.context import bind_actor, get_context
from app.core.errors import UnauthorizedError
from app.modules.identity import repository as repo
from app.modules.identity.container import IdentityServices
from app.modules.identity.models import User, UserStatus
from app.modules.identity.security import recovery_codes, totp
from app.modules.identity.services.access import utcnow
from app.modules.identity.services.sessions import IssuedSession, open_session, revoke_sessions

GENERIC_FAILURE = "Credenciales inválidas o cuenta bloqueada temporalmente."
MFA_RATE_LIMIT, MFA_RATE_WINDOW = 5, 300
EMAIL_RATE_LIMIT, EMAIL_RATE_WINDOW = 10, 900
TOTP_CONTEXT = "identity.totp_credentials.secret"  # AES-GCM associated data of TOTP secrets


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid-credentials"
    title = "No fue posible iniciar sesión"


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    mfa_token: str
    expires_in: int


async def _fail(db: AsyncSession, *, reason: str, user: User | None, email: str) -> NoReturn:
    await record_audit(
        db,
        action="login_failed",
        entity_table="identity.users" if user else None,
        entity_id=str(user.id) if user else None,
        after={"reason": reason, "email": email.lower()},
    )
    await db.commit()
    raise InvalidCredentialsError(GENERIC_FAILURE)


async def _register_failure(
    db: AsyncSession, services: IdentityServices, user: User, *, reason: str, email: str
) -> NoReturn:
    settings = services.settings
    user.failed_login_count += 1
    if user.failed_login_count >= settings.max_failed_logins:
        user.locked_until = utcnow() + timedelta(seconds=settings.lockout_seconds)
        user.failed_login_count = 0
        await db.flush()
        await record_audit(
            db,
            action="account_locked",
            entity_table="identity.users",
            entity_id=str(user.id),
            after={"locked_until": user.locked_until.isoformat()},
        )
    await _fail(db, reason=reason, user=user, email=email)


def _is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > utcnow()


async def login(
    db: AsyncSession,
    services: IdentityServices,
    *,
    email: str,
    password: str,
    device_label: str | None,
) -> IssuedSession | MfaChallenge:
    settings = services.settings
    limiter = services.rate_limiter
    await limiter.hit(
        "login:ip",
        get_context().client_ip or "unknown",
        limit=settings.login_rate_limit_per_ip,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    await limiter.hit(
        "login:email", email, limit=EMAIL_RATE_LIMIT, window_seconds=EMAIL_RATE_WINDOW
    )

    user = await repo.user_by_email(db, email)
    if user is None or user.status != UserStatus.ACTIVE or user.password_hash is None:
        services.passwords.verify(None, password)  # constant work: no account enumeration
        await _fail(db, reason="unknown_or_inactive", user=user, email=email)
    bind_actor(user.id)

    if _is_locked(user):
        services.passwords.verify(None, password)
        await _fail(db, reason="locked", user=user, email=email)
    if not services.passwords.verify(user.password_hash, password):
        await _register_failure(db, services, user, reason="bad_password", email=email)

    user.failed_login_count = 0
    if services.passwords.needs_rehash(user.password_hash):
        user.password_hash = services.passwords.hash(password)

    assert user.id is not None  # noqa: S101
    credential = await repo.totp_of(db, user.id)
    if credential is not None and credential.confirmed_at is not None:
        await db.commit()
        return MfaChallenge(
            mfa_token=services.tokens.issue_mfa_challenge(user_id=user.id),
            expires_in=settings.mfa_challenge_ttl_seconds,
        )

    issued = await open_session(db, services, user, auth_methods=["pwd"], device_label=device_label)
    await record_audit(
        db,
        action="login_succeeded",
        entity_table="identity.user_sessions",
        entity_id=str(issued.session_id),
        after={"auth_methods": ["pwd"], "scope": issued.scope.value},
    )
    await db.commit()
    return issued


async def verify_mfa(
    db: AsyncSession,
    services: IdentityServices,
    *,
    mfa_token: str,
    code: str | None,
    recovery_code: str | None,
    device_label: str | None,
) -> IssuedSession:
    if bool(code) == bool(recovery_code):
        raise InvalidCredentialsError("Envía un código TOTP o un código de recuperación.")
    user_id = services.tokens.decode_mfa_challenge(mfa_token)
    bind_actor(user_id)
    await services.rate_limiter.hit(
        "mfa:user", str(user_id), limit=MFA_RATE_LIMIT, window_seconds=MFA_RATE_WINDOW
    )

    user = await repo.user_by_id(db, user_id, for_update=True)
    if user is None or user.status != UserStatus.ACTIVE or _is_locked(user):
        await _fail(db, reason="mfa_user_unavailable", user=user, email=user.email if user else "")
    credential = await repo.totp_of(db, user_id, for_update=True)
    if credential is None or credential.confirmed_at is None:
        await _fail(db, reason="mfa_not_enrolled", user=user, email=user.email)

    method = "otp"
    if code:
        secret = services.cipher.decrypt(credential.secret_ciphertext, context=TOTP_CONTEXT)
        step = totp.verify(secret, code, last_used_step=credential.last_used_step)
        if step is None:
            await _register_failure(db, services, user, reason="bad_totp", email=user.email)
        credential.last_used_step = step
    else:
        assert recovery_code is not None  # noqa: S101
        if not await _consume_recovery_code(db, services, user_id, recovery_code):
            await _register_failure(
                db, services, user, reason="bad_recovery_code", email=user.email
            )
        method = "recovery_code"

    user.failed_login_count = 0
    issued = await open_session(
        db, services, user, auth_methods=["pwd", "otp"], device_label=device_label
    )
    await record_audit(
        db,
        action="login_succeeded",
        entity_table="identity.user_sessions",
        entity_id=str(issued.session_id),
        after={"auth_methods": ["pwd", "otp"], "second_factor": method},
    )
    await db.commit()
    return issued


async def _consume_recovery_code(
    db: AsyncSession, services: IdentityServices, user_id: uuid.UUID, raw_code: str
) -> bool:
    wanted = recovery_codes.hash_code(services.indexer, raw_code)
    for stored in await repo.unused_recovery_codes(db, user_id):
        if stored.code_hash == wanted:
            stored.used_at = utcnow()
            return True
    return False


async def logout(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await repo.session_by_id(db, session_id, for_update=True)
    if session is not None:
        await revoke_sessions(db, [session], reason="logout")
        await record_audit(
            db, action="logout", entity_table="identity.user_sessions", entity_id=str(session_id)
        )
    await db.commit()
