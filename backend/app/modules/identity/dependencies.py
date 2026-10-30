"""Authentication and authorization dependencies, used by every module's routers.

Each request: verify the access JWT → load user and session in one query (session must be
alive, user active) → load effective permissions → bind the actor to the request context
(logs and audit). Tokens with scope `mfa_enrollment` only reach endpoints that opt in.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.context import bind_actor
from app.core.db.session import SessionDep
from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.identity.container import ServicesDep
from app.modules.identity.models import User, UserSession, UserStatus
from app.modules.identity.security.tokens import TokenScope
from app.modules.identity.services.access import Access, load_access, utcnow
from app.modules.identity.services.scopes import GeoScope, geo_for, scope_covers

_bearer = HTTPBearer(auto_error=False, description="Access token (JWT) de /auth/login.")


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    full_name: str
    session_id: uuid.UUID
    scope: TokenScope
    auth_methods: tuple[str, ...]
    access: Access
    geo: GeoScope
    """The scope for the permission the endpoint requires (`permission(...)`), or for all the
    user's grants on endpoints without one (D-101)."""

    def has(self, permission: str) -> bool:
        """The user holds `permission` somewhere; use `geo_for` to know where."""
        return self.access.has(permission)

    def geo_for(self, permission: str) -> GeoScope:
        return geo_for(self.id, self.access, permission)

    async def holds_within(self, db: AsyncSession, permission: str) -> bool:
        """For a secondary permission (unmask, approve, override): it applies only if its scope
        covers the scope of the permission being exercised (`geo`), so a grant never lends its
        power to another grant's territory (D-101)."""
        if not self.has(permission):
            return False
        return await scope_covers(db, self.geo_for(permission), self.geo)

    def narrowed(self, permission: str) -> "CurrentUser":
        return replace(self, geo=self.geo_for(permission))


class MfaEnrollmentRequiredError(ForbiddenError):
    code = "mfa-enrollment-required"
    title = "Configura tu segundo factor"


async def _authenticate(
    request: Request,
    db: SessionDep,
    services: ServicesDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Falta el token de acceso.")
    claims = services.tokens.decode_access(credentials.credentials)
    row = (
        await db.execute(
            select(User, UserSession)
            .join(UserSession, col(UserSession.user_id) == col(User.id))
            .where(
                col(User.id) == claims.user_id,
                col(UserSession.id) == claims.session_id,
                col(User.deleted_at).is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise UnauthorizedError("Sesión no válida.")
    user, session = row
    if (
        user.status != UserStatus.ACTIVE
        or session.revoked_at is not None
        or session.expires_at <= utcnow()
    ):
        raise UnauthorizedError("Sesión no válida.")
    bind_actor(user.id)
    assert user.id is not None  # noqa: S101
    access = await load_access(db, user.id)
    current = CurrentUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        session_id=claims.session_id,
        scope=claims.scope,
        auth_methods=claims.auth_methods,
        access=access,
        geo=geo_for(user.id, access),
    )
    request.state.current_user = current
    return current


async def current_user_any_scope(
    current: Annotated[CurrentUser, Depends(_authenticate)],
) -> CurrentUser:
    """For MFA-enrollment, logout and profile endpoints."""
    return current


async def current_user(current: Annotated[CurrentUser, Depends(_authenticate)]) -> CurrentUser:
    if current.scope is not TokenScope.FULL:
        raise MfaEnrollmentRequiredError(
            "Tu rol exige segundo factor. Configura tu autenticador para continuar."
        )
    return current


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
AnyScopeUserDep = Annotated[CurrentUser, Depends(current_user_any_scope)]


def require_permission(permission: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def dependency(current: CurrentUserDep) -> CurrentUser:
        if not current.has(permission):
            raise ForbiddenError(f"No tienes el permiso «{permission}».")
        return current.narrowed(permission)

    dependency.__name__ = f"require_{permission.replace('.', '_')}"
    return dependency


def permission(code: str) -> object:
    """Route-level authorization: ``user: Annotated[CurrentUser, permission(Perm.USER_READ)]``."""
    return Depends(require_permission(code))
