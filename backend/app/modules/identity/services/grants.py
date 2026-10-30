"""Grants (D-101): create and remove (role, scope) pairs, with anti-escalation per pair.

Shared by manual administration (`admin.set_user_grants`) and, later, by the grants that
appointments originate (D-104). Changes go through the ORM so they reach the audit log.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError
from app.modules.identity import repository as repo
from app.modules.identity.models import (
    SCOPE_COLUMNS,
    GrantOrigin,
    Role,
    ScopeLevel,
    UserGrant,
    UserGrantScope,
)
from app.modules.identity.services.access import Access, ensure_can_assign, group_by_grants
from app.modules.identity.services.scopes import (
    active_framework,
    ensure_node_within,
    geo_for,
    grant_scopes,
    rebuild_grant_sections,
    validate_node,
)

ScopeSpec = tuple[ScopeLevel, uuid.UUID | None]


@dataclass(frozen=True, slots=True)
class GrantView:
    grant: UserGrant
    role: Role
    scopes: list[UserGrantScope]


def scope_key(scope: UserGrantScope) -> ScopeSpec:
    level = ScopeLevel(scope.scope_level)
    node = None if level == ScopeLevel.NATIONAL else getattr(scope, SCOPE_COLUMNS[level])
    return level, node


async def grants_of(db: AsyncSession, user_id: uuid.UUID) -> list[GrantView]:
    rows = (
        await db.execute(
            select(UserGrant, Role)
            .join(Role, col(Role.id) == col(UserGrant.role_id))
            .where(col(UserGrant.user_id) == user_id)
            .order_by(col(UserGrant.created_at), col(UserGrant.id))
        )
    ).all()
    return [
        GrantView(grant=grant, role=role, scopes=await grant_scopes(db, pk(grant)))
        for grant, role in rows
    ]


async def validate_scopes(db: AsyncSession, scopes: list[ScopeSpec]) -> list[ScopeSpec]:
    """Checks shape and existence in the active framework; returns them deduplicated."""
    unique = list(dict.fromkeys(scopes))
    framework_id = None
    for level, node in unique:
        if level == ScopeLevel.NATIONAL:
            if node is not None:
                raise BadRequestError("El alcance nacional no lleva nodo.")
            continue
        if node is None:
            raise BadRequestError(f"El alcance {level.value} requiere un nodo.")
        framework_id = framework_id or await active_framework(db)
        await validate_node(db, level, node, framework_id)
    if any(level == ScopeLevel.NATIONAL for level, _ in unique) and len(unique) > 1:
        raise BadRequestError("El alcance nacional ya incluye todo; no lo combines con otros.")
    return unique


async def ensure_can_hand_out(
    db: AsyncSession, actor_id: uuid.UUID, actor: Access, role: Role, scopes: list[ScopeSpec]
) -> None:
    """D-101: the actor holds every permission of the role, and for each one the scopes are
    inside the actor's scope *for that permission*."""
    await ensure_can_assign(db, actor, [role])
    if actor.grants_all:
        return
    assert role.id is not None  # noqa: S101 - persisted role
    codes = await repo.permission_codes_of_role(db, role.id)
    for permissions in group_by_grants(actor, codes).values():
        geo = geo_for(actor_id, actor, permissions[0])
        for level, node in scopes:
            await ensure_node_within(db, geo, level, node)


async def add_grant(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: Role,
    scopes: list[ScopeSpec],
    origin: GrantOrigin = GrantOrigin.MANUAL,
    source_id: uuid.UUID | None = None,
    assigned_by: uuid.UUID | None = None,
) -> UserGrant:
    """Creates the grant, its scopes and its sections (caller validated and commits)."""
    grant = UserGrant(
        user_id=user_id,
        role_id=role.id,  # type: ignore[arg-type]
        origin=origin,
        source_id=source_id,
        assigned_by_user_id=assigned_by,
    )
    db.add(grant)
    await db.flush()
    await replace_scopes(db, grant, scopes)
    return grant


async def replace_scopes(db: AsyncSession, grant: UserGrant, scopes: list[ScopeSpec]) -> None:
    assert grant.id is not None  # noqa: S101 - flushed
    for previous in await grant_scopes(db, grant.id):
        await db.delete(previous)
    await db.flush()
    for level, node in scopes:
        values: dict[str, object] = {"grant_id": grant.id, "scope_level": level}
        if node is not None:
            values[SCOPE_COLUMNS[level]] = node
        db.add(UserGrantScope(**values))  # type: ignore[arg-type]
    await db.flush()
    await rebuild_grant_sections(db, grant.id)


async def remove_grant(db: AsyncSession, grant: UserGrant) -> None:
    """ORM deletes (not the FK cascade) so the removed scopes stay in the audit log (D-45)."""
    assert grant.id is not None  # noqa: S101 - persisted
    for scope in await grant_scopes(db, grant.id):
        await db.delete(scope)
    await db.flush()  # scopes first: without ORM relationships the unit of work has no order
    await db.delete(grant)
    await db.flush()
