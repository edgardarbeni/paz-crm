"""Sessions and refresh-token rotation.

- One `UserSession` per device. Each refresh rotates the opaque refresh token (the old one is
  marked used and the new one points to it).
- Presenting a token that was already used or revoked means it leaked: the whole session is
  revoked (refresh-token reuse detection, RFC 6819 §5.2.2.3 / OAuth 2.0 Security BCP).
- Access tokens carry the session id and every authenticated request loads the session
  together with the user (one indexed query), so revoking a session takes effect on the very
  next request without waiting for the access token to expire.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.context import bind_actor, get_context
from app.core.errors import UnauthorizedError
from app.modules.identity import repository as repo
from app.modules.identity.container import IdentityServices
from app.modules.identity.models import RefreshToken, User, UserSession, UserStatus
from app.modules.identity.security.tokens import TokenScope, hash_opaque_token, new_opaque_token
from app.modules.identity.services.access import load_access, utcnow


class InvalidRefreshError(UnauthorizedError):
    code = "invalid-refresh-token"
    title = "Sesión expirada"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_id: uuid.UUID
    access_token: str
    refresh_token: str
    scope: TokenScope
    expires_in: int


async def scope_for(db: AsyncSession, user: User, auth_methods: list[str]) -> TokenScope:
    assert user.id is not None  # noqa: S101
    access = await load_access(db, user.id)
    if access.requires_mfa and "otp" not in auth_methods:
        return TokenScope.MFA_ENROLLMENT
    return TokenScope.FULL


def _access_token(
    services: IdentityServices, user: User, session: UserSession, scope: TokenScope
) -> str:
    assert user.id is not None  # noqa: S101
    assert session.id is not None  # noqa: S101
    return services.tokens.issue_access(
        user_id=user.id, session_id=session.id, scope=scope, auth_methods=session.auth_methods
    )


async def _new_refresh(
    db: AsyncSession, services: IdentityServices, session: UserSession, parent: RefreshToken | None
) -> str:
    assert session.id is not None  # noqa: S101
    raw, token_hash = new_opaque_token()
    ttl = timedelta(seconds=services.settings.refresh_token_ttl_seconds)
    db.add(
        RefreshToken(
            session_id=session.id,
            token_hash=token_hash,
            parent_token_id=parent.id if parent else None,
            expires_at=min(utcnow() + ttl, session.expires_at),
        )
    )
    await db.flush()
    return raw


async def open_session(
    db: AsyncSession,
    services: IdentityServices,
    user: User,
    *,
    auth_methods: list[str],
    device_label: str | None,
) -> IssuedSession:
    """Creates the session, its first refresh token and an access token (caller commits)."""
    assert user.id is not None  # noqa: S101
    context = get_context()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        device_label=device_label,
        user_agent=(context.user_agent or "")[:500] or None,
        ip_address=context.client_ip,
        auth_methods=auth_methods,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=services.settings.session_absolute_ttl_seconds),
    )
    db.add(session)
    await db.flush()
    refresh = await _new_refresh(db, services, session, parent=None)
    user.last_login_at = now
    scope = await scope_for(db, user, auth_methods)
    assert session.id is not None  # noqa: S101
    return IssuedSession(
        session_id=session.id,
        access_token=_access_token(services, user, session, scope),
        refresh_token=refresh,
        scope=scope,
        expires_in=int(services.tokens.access_ttl.total_seconds()),
    )


async def refresh(db: AsyncSession, services: IdentityServices, raw_token: str) -> IssuedSession:
    now = utcnow()
    token = await repo.refresh_token_by_hash(db, hash_opaque_token(raw_token))
    if token is None:
        raise InvalidRefreshError()
    session = await repo.session_by_id(db, token.session_id, for_update=True)
    if session is None:
        raise InvalidRefreshError()
    bind_actor(session.user_id)

    if token.used_at is not None or token.revoked_at is not None:
        if session.revoked_at is None:
            await revoke_sessions(db, [session], reason="refresh_reuse")
        await record_audit(
            db,
            action="refresh_reuse_detected",
            entity_table="identity.user_sessions",
            entity_id=str(session.id),
        )
        await db.commit()
        raise InvalidRefreshError("Se detectó el reuso de un token; la sesión fue cerrada.")

    if session.revoked_at is not None or session.expires_at <= now or token.expires_at <= now:
        raise InvalidRefreshError()

    user = await repo.user_by_id(db, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidRefreshError()

    token.used_at = now
    new_raw = await _new_refresh(db, services, session, parent=token)
    session.last_seen_at = now
    session.ip_address = get_context().client_ip
    scope = await scope_for(db, user, session.auth_methods)
    access_token = _access_token(services, user, session, scope)
    await db.commit()
    assert session.id is not None  # noqa: S101
    return IssuedSession(
        session_id=session.id,
        access_token=access_token,
        refresh_token=new_raw,
        scope=scope,
        expires_in=int(services.tokens.access_ttl.total_seconds()),
    )


async def revoke_sessions(db: AsyncSession, sessions: list[UserSession], *, reason: str) -> int:
    """Revokes sessions and their refresh tokens (caller commits); returns how many."""
    now = utcnow()
    live = [session for session in sessions if session.revoked_at is None]
    for session in live:
        session.revoked_at = now
        session.revoke_reason = reason
    await db.flush()
    await repo.revoke_session_tokens(db, [s.id for s in live if s.id is not None], now)
    return len(live)


async def revoke_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    reason: str,
    except_session_id: uuid.UUID | None = None,
) -> int:
    sessions = [
        session
        for session in await repo.active_sessions(db, user_id, utcnow())
        if session.id != except_session_id
    ]
    return await revoke_sessions(db, sessions, reason=reason)
