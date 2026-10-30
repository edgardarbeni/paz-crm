"""Who sees which member (D-83, D-101): geographic scope OR branch scope, per grant.

- Geographic: the member's home section is in the sections of the grants that give the
  permission being exercised (D-34, D-101).
- Branch: the member is inside the network of a node assigned to one of those grants in
  `user_branch_scopes` (`path <@ branch.path`), across states. A branch extends a grant, so it
  only reaches what that grant's role allows.
- Anti-escalation: a branch is only granted on a node inside a branch the actor already has
  (or by an unrestricted actor), and only on a grant whose Peace Movement permissions the
  actor holds. Seeing
  the node through its address is not enough, because its subtree may cross into states the
  actor cannot see.
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, cast, exists, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.modules.identity import repository as identity_repo
from app.modules.identity.models import UserGrant
from app.modules.identity.services.access import Access, ensure_can_grant
from app.modules.identity.services.scopes import GeoScope, ensure_within_scope
from app.modules.peace_movement.models import Ltree, Member, UserBranchScope

MODULE_PREFIX = "peace_movement."


def _branch_filter(grant_ids: tuple[uuid.UUID, ...], path: Any) -> ColumnElement[bool]:
    branch = aliased(Member)
    return exists().where(
        col(UserBranchScope.grant_id).in_(grant_ids),
        col(UserBranchScope.deleted_at).is_(None),
        col(branch.id) == col(UserBranchScope.member_id),
        path.op("<@")(branch.path),
    )


def member_visibility(geo: GeoScope, member: Any = Member) -> ColumnElement[bool] | None:
    """SQL filter over `member` (the entity or an alias); None when unrestricted."""
    if geo.unrestricted:
        return None
    geographic = geo.sections_filter(member.section_id)
    assert geographic is not None  # noqa: S101 - restricted scopes always filter
    return or_(geographic, _branch_filter(geo.grant_ids, member.path))


async def in_branch(db: AsyncSession, geo: GeoScope, member: Member) -> bool:
    """True if `member` is inside one of the user's branches (or the user is unrestricted)."""
    if geo.unrestricted:
        return True
    if not geo.grant_ids:
        return False
    found = await db.execute(
        select(col(UserBranchScope.id)).where(_branch_filter(geo.grant_ids, _literal(member)))
    )
    return found.first() is not None


def _literal(member: Member) -> Any:
    return cast(literal(member.path), Ltree())


async def branches_of(db: AsyncSession, grant_id: uuid.UUID) -> list[UserBranchScope]:
    rows = await db.execute(
        select(UserBranchScope)
        .where(col(UserBranchScope.grant_id) == grant_id, col(UserBranchScope.deleted_at).is_(None))
        .order_by(col(UserBranchScope.created_at))
    )
    return list(rows.scalars())


async def grant_in_scope(db: AsyncSession, actor: GeoScope, grant_id: uuid.UUID) -> UserGrant:
    """The grant exists and its user is inside the actor's scope."""
    grant = await db.get(UserGrant, grant_id)
    if grant is None:
        raise NotFoundError("Concesión no encontrada.")
    await ensure_within_scope(db, actor, user_id=grant.user_id)
    return grant


async def set_branches(
    db: AsyncSession,
    actor: GeoScope,
    actor_access: Access,
    grant_id: uuid.UUID,
    member_ids: list[uuid.UUID],
) -> list[UserBranchScope]:
    """Replaces the grant's branches (caller commits). Changes go through the ORM (audited)."""
    grant = await grant_in_scope(db, actor, grant_id)
    # A branch only widens the grant's Peace Movement permissions: the actor must hold them.
    reach = {
        code
        for code in await identity_repo.permission_codes_of_role(db, grant.role_id)
        if code.startswith(MODULE_PREFIX)
    }
    ensure_can_grant(actor_access, reach)
    wanted = list(dict.fromkeys(member_ids))
    if len(wanted) != len(member_ids):
        raise BadRequestError("Hay pacificadores repetidos en la lista.")
    for member_id in wanted:
        member = await db.get(Member, member_id)
        if member is None or member.deleted_at is not None:
            raise NotFoundError(f"Pacificador {member_id} no encontrado.")
        if not await in_branch(db, actor, member):
            raise ForbiddenError(
                "Solo puedes otorgar ramas dentro de una rama que ya tienes asignada."
            )
    current = {branch.member_id: branch for branch in await branches_of(db, grant_id)}
    for member_id, branch in current.items():
        if member_id not in wanted:
            await db.delete(branch)
    for member_id in wanted:
        if member_id not in current:
            db.add(UserBranchScope(grant_id=grant_id, member_id=member_id))
    await db.flush()
    return await branches_of(db, grant_id)
