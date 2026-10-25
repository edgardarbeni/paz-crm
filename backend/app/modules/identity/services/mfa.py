"""TOTP enrollment and recovery codes (D-33: mandatory for roles with `requires_mfa`)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.audit import record_audit
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.modules.identity import repository as repo
from app.modules.identity.container import IdentityServices
from app.modules.identity.models import RecoveryCode, TotpCredential, User
from app.modules.identity.security import recovery_codes, totp
from app.modules.identity.services.access import load_access, utcnow
from app.modules.identity.services.auth import TOTP_CONTEXT, InvalidCredentialsError
from app.modules.identity.services.sessions import revoke_user_sessions, scope_for


class InvalidTotpCodeError(BadRequestError):
    code = "invalid-totp-code"
    title = "Código inválido"


@dataclass(frozen=True, slots=True)
class TotpSetup:
    secret: str
    otpauth_uri: str
    qr_svg: str


@dataclass(frozen=True, slots=True)
class TotpConfirmed:
    recovery_codes: list[str]
    access_token: str
    expires_in: int


async def _user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await repo.user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")
    return user


async def setup_totp(
    db: AsyncSession, services: IdentityServices, *, user_id: uuid.UUID
) -> TotpSetup:
    user = await _user(db, user_id)
    credential = await repo.totp_of(db, user_id, for_update=True)
    if credential is not None and credential.confirmed_at is not None:
        raise ConflictError("Ya tienes un autenticador configurado; desactívalo para cambiarlo.")
    secret = totp.new_secret()
    ciphertext = services.cipher.encrypt(secret, context=TOTP_CONTEXT)
    key_version = services.cipher.key_version(ciphertext)
    if credential is None:
        db.add(
            TotpCredential(user_id=user_id, secret_ciphertext=ciphertext, key_version=key_version)
        )
    else:  # restart a pending enrollment with a fresh secret
        credential.secret_ciphertext = ciphertext
        credential.key_version = key_version
        credential.last_used_step = None
    await db.commit()
    uri = totp.provisioning_uri(secret, account=user.email, issuer=services.settings.totp_issuer)
    return TotpSetup(secret=secret, otpauth_uri=uri, qr_svg=totp.qr_svg_data_uri(uri))


async def confirm_totp(
    db: AsyncSession,
    services: IdentityServices,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    code: str,
) -> TotpConfirmed:
    user = await _user(db, user_id)
    credential = await repo.totp_of(db, user_id, for_update=True)
    if credential is None or credential.confirmed_at is not None:
        raise ConflictError("No hay un enrolamiento pendiente. Inicia la configuración de nuevo.")
    secret = services.cipher.decrypt(credential.secret_ciphertext, context=TOTP_CONTEXT)
    step = totp.verify(secret, code, last_used_step=credential.last_used_step)
    if step is None:
        raise InvalidTotpCodeError("El código no es válido. Revisa la hora de tu dispositivo.")
    credential.confirmed_at = utcnow()
    credential.last_used_step = step
    codes = await _replace_recovery_codes(db, services, user_id)

    # The user just proved possession of the second factor: upgrade the current session.
    session = await repo.session_by_id(db, session_id, for_update=True)
    assert session is not None  # noqa: S101
    assert session.id is not None  # noqa: S101
    if "otp" not in session.auth_methods:
        session.auth_methods = [*session.auth_methods, "otp"]
    scope = await scope_for(db, user, session.auth_methods)
    access_token = services.tokens.issue_access(
        user_id=user_id, session_id=session.id, scope=scope, auth_methods=session.auth_methods
    )
    await record_audit(
        db, action="mfa_enrolled", entity_table="identity.users", entity_id=str(user_id)
    )
    await db.commit()
    return TotpConfirmed(
        recovery_codes=codes,
        access_token=access_token,
        expires_in=int(services.tokens.access_ttl.total_seconds()),
    )


async def disable_totp(
    db: AsyncSession, services: IdentityServices, *, user_id: uuid.UUID, password: str, code: str
) -> None:
    user = await _user(db, user_id)
    if (await load_access(db, user_id)).requires_mfa:
        raise ConflictError("Tu rol exige segundo factor; no puedes desactivarlo.")
    if not services.passwords.verify(user.password_hash, password):
        raise InvalidCredentialsError("La contraseña no es correcta.")
    await _verify_confirmed_code(db, services, user_id, code)
    await _remove_mfa(db, user_id)
    await record_audit(
        db, action="mfa_disabled", entity_table="identity.users", entity_id=str(user_id)
    )
    await db.commit()


async def regenerate_recovery_codes(
    db: AsyncSession, services: IdentityServices, *, user_id: uuid.UUID, code: str
) -> list[str]:
    await _user(db, user_id)
    await _verify_confirmed_code(db, services, user_id, code)
    codes = await _replace_recovery_codes(db, services, user_id)
    await record_audit(
        db,
        action="recovery_codes_regenerated",
        entity_table="identity.users",
        entity_id=str(user_id),
    )
    await db.commit()
    return codes


async def admin_reset_mfa(db: AsyncSession, *, target_id: uuid.UUID) -> None:
    """Removes the target's authenticator and recovery codes and closes their sessions; their
    next login asks for a new enrollment if their role requires MFA."""
    await _user(db, target_id)
    await _remove_mfa(db, target_id)
    await revoke_user_sessions(db, target_id, reason="mfa_reset")
    await record_audit(
        db, action="mfa_reset", entity_table="identity.users", entity_id=str(target_id)
    )
    await db.commit()


async def _verify_confirmed_code(
    db: AsyncSession, services: IdentityServices, user_id: uuid.UUID, code: str
) -> None:
    credential = await repo.totp_of(db, user_id, for_update=True)
    if credential is None or credential.confirmed_at is None:
        raise ConflictError("No tienes un autenticador configurado.")
    secret = services.cipher.decrypt(credential.secret_ciphertext, context=TOTP_CONTEXT)
    step = totp.verify(secret, code, last_used_step=credential.last_used_step)
    if step is None:
        raise InvalidTotpCodeError("El código no es válido.")
    credential.last_used_step = step


async def _replace_recovery_codes(
    db: AsyncSession, services: IdentityServices, user_id: uuid.UUID
) -> list[str]:
    # Old codes are removed in bulk (they are secrets; the regeneration itself is audited).
    await db.execute(delete(RecoveryCode).where(col(RecoveryCode.user_id) == user_id))
    codes = recovery_codes.generate()
    for code in codes:
        db.add(
            RecoveryCode(
                user_id=user_id, code_hash=recovery_codes.hash_code(services.indexer, code)
            )
        )
    await db.flush()
    return codes


async def _remove_mfa(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(RecoveryCode).where(col(RecoveryCode.user_id) == user_id))
    credential = await repo.totp_of(db, user_id, for_update=True)
    if credential is not None:
        await db.delete(credential)
    await db.flush()
