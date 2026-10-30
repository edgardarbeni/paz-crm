"""Password change, password reset and invitations (D-35)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.audit import record_audit
from app.core.context import bind_actor, get_context
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.mail import OutgoingEmail
from app.modules.identity import emails
from app.modules.identity import repository as repo
from app.modules.identity.container import IdentityServices
from app.modules.identity.models import (
    PasswordResetToken,
    User,
    UserGrant,
    UserInvitation,
    UserStatus,
)
from app.modules.identity.security.tokens import hash_opaque_token, new_opaque_token
from app.modules.identity.services.access import Access, ensure_can_assign, utcnow
from app.modules.identity.services.auth import InvalidCredentialsError
from app.modules.identity.services.sessions import revoke_user_sessions

RESET_RATE_LIMIT, RESET_RATE_WINDOW = 5, 3600


class InvalidLinkError(BadRequestError):
    code = "invalid-link"
    title = "Enlace inválido o vencido"


# --- password change & reset ------------------------------------------------------------


async def change_password(
    db: AsyncSession,
    services: IdentityServices,
    *,
    user_id: uuid.UUID,
    current_session_id: uuid.UUID,
    current_password: str,
    new_password: str,
) -> None:
    user = await repo.user_by_id(db, user_id, for_update=True)
    assert user is not None  # noqa: S101 - authenticated user
    if not services.passwords.verify(user.password_hash, current_password):
        raise InvalidCredentialsError("La contraseña actual no es correcta.")
    services.passwords.validate(new_password, email=user.email)
    _set_password(services, user, new_password)
    revoked = await revoke_user_sessions(
        db, user_id, reason="password_changed", except_session_id=current_session_id
    )
    await record_audit(
        db,
        action="password_changed",
        entity_table="identity.users",
        entity_id=str(user_id),
        after={"other_sessions_revoked": revoked},
    )
    await db.commit()


async def request_password_reset(
    db: AsyncSession, services: IdentityServices, *, email: str
) -> OutgoingEmail | None:
    """Always succeeds from the caller's point of view (no account enumeration). Returns the
    e-mail to send in the background, if any."""
    limiter = services.rate_limiter
    await limiter.hit(
        "reset:ip", get_context().client_ip or "unknown", limit=20, window_seconds=RESET_RATE_WINDOW
    )
    await limiter.hit(
        "reset:email", email, limit=RESET_RATE_LIMIT, window_seconds=RESET_RATE_WINDOW
    )

    user = await repo.user_by_email(db, email)
    if user is None or user.status != UserStatus.ACTIVE:
        await record_audit(
            db, action="password_reset_requested", after={"email": email.lower(), "sent": False}
        )
        await db.commit()
        return None
    assert user.id is not None  # noqa: S101
    bind_actor(user.id)
    raw, token_hash = new_opaque_token()
    ttl = timedelta(seconds=services.settings.password_reset_ttl_seconds)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            requested_ip=get_context().client_ip,
            expires_at=utcnow() + ttl,
        )
    )
    await db.commit()
    return emails.password_reset(
        base_url=services.settings.public_base_url,
        to=user.email,
        full_name=user.full_name,
        token=raw,
        ttl=ttl,
    )


async def reset_password(
    db: AsyncSession, services: IdentityServices, *, token: str, new_password: str
) -> None:
    now = utcnow()
    result = await db.execute(
        select(PasswordResetToken)
        .where(col(PasswordResetToken.token_hash) == hash_opaque_token(token))
        .with_for_update()
    )
    reset = result.scalar_one_or_none()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise InvalidLinkError("El enlace para restablecer la contraseña no es válido o venció.")
    user = await repo.user_by_id(db, reset.user_id, for_update=True)
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidLinkError()
    bind_actor(user.id)
    services.passwords.validate(new_password, email=user.email)

    _set_password(services, user, new_password)
    user.failed_login_count = 0
    user.locked_until = None
    reset.used_at = now
    # Any other outstanding reset link for this user stops working too.
    others = await db.execute(
        select(PasswordResetToken).where(
            col(PasswordResetToken.user_id) == user.id,
            col(PasswordResetToken.used_at).is_(None),
            col(PasswordResetToken.id) != reset.id,
        )
    )
    for other in others.scalars():
        other.used_at = now
    assert user.id is not None  # noqa: S101
    await revoke_user_sessions(db, user.id, reason="password_reset")
    await db.commit()


def _set_password(services: IdentityServices, user: User, password: str) -> None:
    user.password_hash = services.passwords.hash(password)
    user.password_changed_at = utcnow()


# --- invitations -------------------------------------------------------------------------


async def invite_user(
    db: AsyncSession,
    services: IdentityServices,
    *,
    actor_id: uuid.UUID,
    actor: Access,
    email: str,
    full_name: str,
    role_ids: list[uuid.UUID],
) -> tuple[User, UserInvitation, OutgoingEmail]:
    if await repo.user_by_email(db, email) is not None:
        raise ConflictError("Ya existe un usuario con ese correo.")
    roles = await repo.roles_by_ids(db, role_ids)
    if len(roles) != len(set(role_ids)):
        raise BadRequestError("Uno o más roles no existen.")
    await ensure_can_assign(db, actor, roles)

    user = User(email=email, full_name=full_name, status=UserStatus.INVITED)
    db.add(user)
    await db.flush()
    assert user.id is not None  # noqa: S101
    for role in roles:
        assert role.id is not None  # noqa: S101
        # Without scope the grant sees nothing until an admin sets it (deny by default).
        db.add(UserGrant(user_id=user.id, role_id=role.id, assigned_by_user_id=actor_id))
    invitation, message = await _issue_invitation(db, services, user, invited_by=actor_id)
    await db.commit()
    return user, invitation, message


async def resend_invitation(
    db: AsyncSession, services: IdentityServices, *, actor_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[User, UserInvitation, OutgoingEmail]:
    user = await repo.user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")
    if user.status != UserStatus.INVITED:
        raise ConflictError("El usuario ya activó su cuenta.")
    invitation, message = await _issue_invitation(db, services, user, invited_by=actor_id)
    await db.commit()
    return user, invitation, message


async def _issue_invitation(
    db: AsyncSession, services: IdentityServices, user: User, *, invited_by: uuid.UUID
) -> tuple[UserInvitation, OutgoingEmail]:
    assert user.id is not None  # noqa: S101
    now = utcnow()
    for previous in await repo.pending_invitations(db, user.id):
        previous.revoked_at = now
    raw, token_hash = new_opaque_token()
    ttl = timedelta(seconds=services.settings.invitation_ttl_seconds)
    invitation = UserInvitation(
        user_id=user.id, token_hash=token_hash, invited_by_user_id=invited_by, expires_at=now + ttl
    )
    db.add(invitation)
    await db.flush()
    message = emails.invitation(
        base_url=services.settings.public_base_url,
        to=user.email,
        full_name=user.full_name,
        token=raw,
        ttl=ttl,
    )
    return invitation, message


# Public for modules that create accounts (party structure, D-104).
issue_invitation = _issue_invitation


async def _valid_invitation(db: AsyncSession, token: str) -> tuple[UserInvitation, User]:
    invitation = await repo.invitation_by_hash(db, hash_opaque_token(token))
    now = utcnow()
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= now
    ):
        raise InvalidLinkError("La invitación no es válida o venció.")
    user = await repo.user_by_id(db, invitation.user_id, for_update=True)
    if user is None or user.status != UserStatus.INVITED:
        raise InvalidLinkError("La invitación no es válida o venció.")
    return invitation, user


async def inspect_invitation(db: AsyncSession, *, token: str) -> tuple[str, str, datetime]:
    """Returns (email, full_name, expires_at) of a valid invitation."""
    invitation, user = await _valid_invitation(db, token)
    details = (user.email, user.full_name, invitation.expires_at)
    await db.rollback()  # read-only: release the row locks (expires the loaded objects)
    return details


async def accept_invitation(
    db: AsyncSession,
    services: IdentityServices,
    *,
    token: str,
    password: str,
    full_name: str | None,
) -> None:
    invitation, user = await _valid_invitation(db, token)
    bind_actor(user.id)
    services.passwords.validate(password, email=user.email)
    if full_name:
        user.full_name = full_name
    _set_password(services, user, password)
    user.status = UserStatus.ACTIVE
    invitation.accepted_at = utcnow()
    await db.commit()
