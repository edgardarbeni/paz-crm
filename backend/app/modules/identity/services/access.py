"""Effective permissions, grants (D-101) and privilege-escalation rules.

A user's access is the sum of their grants. Each grant is a (role, scope) pair: the role's
permissions apply only inside that grant's scope. So the scope a user has *for a permission*
is the union of the scopes of the grants whose role includes it (`Access.geo_for`).
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import ForbiddenError
from app.core.modules import permission_codes
from app.modules.identity import repository as repo
from app.modules.identity.models import (
    GrantOrigin,
    Role,
    ScopeLevel,
    UserGrant,
    UserGrantScope,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Grant:
    """A loaded grant: its role, the role's permissions and whether its scope is national."""

    id: uuid.UUID
    role: Role
    permissions: frozenset[str]
    national: bool
    origin: GrantOrigin = GrantOrigin.MANUAL


@dataclass(frozen=True, slots=True)
class Access:
    """What a user may do. `grants_all` (superadmin) implies every permission everywhere."""

    grants: tuple[Grant, ...]

    @property
    def roles(self) -> tuple[Role, ...]:
        return tuple({grant.role.id: grant.role for grant in self.grants}.values())

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset().union(*(grant.permissions for grant in self.grants))

    @property
    def grants_all(self) -> bool:
        return any(grant.role.grants_all for grant in self.grants)

    @property
    def requires_mfa(self) -> bool:
        return self.grants_all or any(role.requires_mfa for role in self.roles)

    def has(self, permission: str) -> bool:
        """True if some grant includes `permission` (anywhere; see `grants_for` for where)."""
        return self.grants_all or permission in self.permissions

    def grants_for(self, permission: str | None) -> tuple[Grant, ...]:
        """The grants whose role includes `permission` (all grants for None)."""
        if permission is None:
            return self.grants
        return tuple(
            grant
            for grant in self.grants
            if grant.role.grants_all or permission in grant.permissions
        )

    def effective_permissions(self) -> list[str]:
        return sorted(permission_codes() if self.grants_all else self.permissions)


async def load_access(db: AsyncSession, user_id: uuid.UUID) -> Access:
    rows = (
        await db.execute(
            select(UserGrant, Role)
            .join(Role, col(Role.id) == col(UserGrant.role_id))
            .where(col(UserGrant.user_id) == user_id, repo.alive(Role))
            .order_by(col(UserGrant.created_at), col(UserGrant.id))
        )
    ).all()
    if not rows:
        return Access(grants=())
    by_role = await repo.permission_codes_by_role(db, {role.id for _, role in rows if role.id})
    grant_ids = [grant.id for grant, _ in rows]
    national = set(
        (
            await db.execute(
                select(col(UserGrantScope.grant_id)).where(
                    col(UserGrantScope.grant_id).in_(grant_ids),
                    col(UserGrantScope.scope_level) == ScopeLevel.NATIONAL,
                )
            )
        ).scalars()
    )
    return Access(
        grants=tuple(
            Grant(
                id=grant.id,  # type: ignore[arg-type]
                role=role,
                permissions=frozenset(by_role.get(role.id, set())),  # type: ignore[arg-type]
                national=grant.id in national,
                origin=GrantOrigin(grant.origin),
            )
            for grant, role in rows
        )
    )


async def ensure_can_assign(db: AsyncSession, actor: Access, roles: Iterable[Role]) -> None:
    """A user can only hand out roles whose powers they already hold (no escalation). The
    geographic half of the rule (D-101) is in `grants.ensure_can_hand_out`."""
    if actor.grants_all:
        return
    for role in roles:
        if role.grants_all:
            raise ForbiddenError(f"No puedes asignar el rol «{role.name}».")
        assert role.id is not None  # noqa: S101 - persisted roles
        missing = await repo.permission_codes_of_role(db, role.id) - actor.permissions
        if missing:
            raise ForbiddenError(
                f"No puedes asignar el rol «{role.name}»: incluye permisos que no tienes."
            )


def ensure_can_grant(actor: Access, permissions: Iterable[str]) -> None:
    if actor.grants_all:
        return
    missing = set(permissions) - actor.permissions
    if missing:
        raise ForbiddenError(
            "No puedes otorgar permisos que no tienes: " + ", ".join(sorted(missing)) + "."
        )


def group_by_grants(
    actor: Access, permissions: Iterable[str]
) -> dict[tuple[uuid.UUID, ...], list[str]]:
    """Permissions grouped by the set of actor grants that provide them (to check each scope
    once)."""
    groups: dict[tuple[uuid.UUID, ...], list[str]] = defaultdict(list)
    for code in permissions:
        groups[tuple(grant.id for grant in actor.grants_for(code))].append(code)
    return groups
