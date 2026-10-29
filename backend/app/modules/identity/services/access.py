"""Effective permissions and privilege-escalation rules."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.modules import permission_codes
from app.modules.identity import repository as repo
from app.modules.identity.models import Role


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Access:
    """What a user may do. `grants_all` (superadmin) implies every permission."""

    roles: tuple[Role, ...]
    permissions: frozenset[str]
    grants_all: bool

    @property
    def requires_mfa(self) -> bool:
        return self.grants_all or any(role.requires_mfa for role in self.roles)

    def has(self, permission: str) -> bool:
        return self.grants_all or permission in self.permissions

    def effective_permissions(self) -> list[str]:
        return sorted(permission_codes() if self.grants_all else self.permissions)


async def load_access(db: AsyncSession, user_id: uuid.UUID) -> Access:
    roles = await repo.roles_of(db, user_id)
    return Access(
        roles=tuple(roles),
        permissions=frozenset(await repo.permission_codes_of(db, user_id)),
        grants_all=any(role.grants_all for role in roles),
    )


async def ensure_can_assign(db: AsyncSession, actor: Access, roles: Iterable[Role]) -> None:
    """A user can only hand out roles whose powers they already hold (no escalation)."""
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
