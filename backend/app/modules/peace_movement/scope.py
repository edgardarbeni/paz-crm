"""Who sees which member (D-83): geographic scope OR branch scope.

- Geographic: the member's home section is in the user's sections (D-34).
- Branch: the member is inside the network of a node assigned to the user in
  `user_branch_scopes` (`path <@ branch.path`), across states.
- Anti-escalation: a branch is only granted on a node inside a branch the actor already has
  (or by an unrestricted actor). Seeing the node through its address is not enough, because its
  subtree may cross into states the actor cannot see.
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, cast, exists, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.modules.identity.services.scopes import GeoScope, ensure_within_scope
from app.modules.peace_movement.models import Ltree, Member, UserBranchScope


def _branch_filter(user_id: uuid.UUID, path: Any) -> ColumnElement[bool]:
    branch = aliased(Member)
    return exists().where(
        col(UserBranchScope.user_id) == user_id,
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
    return or_(geographic, _branch_filter(geo.user_id, member.path))


async def in_branch(db: AsyncSession, geo: GeoScope, member: Member) -> bool:
    """True if `member` is inside one of the user's branches (or the user is unrestricted)."""
    if geo.unrestricted:
        return True
    found = await db.execute(
        select(col(UserBranchScope.id)).where(_branch_filter(geo.user_id, _literal(member)))
    )
    return found.first() is not None


def _literal(member: Member) -> Any:
    return cast(literal(member.path), Ltree())


async def branches_of(db: AsyncSession, user_id: uuid.UUID) -> list[UserBranchScope]:
    rows = await db.execute(
        select(UserBranchScope)
        .where(col(UserBranchScope.user_id) == user_id, col(UserBranchScope.deleted_at).is_(None))
        .order_by(col(UserBranchScope.created_at))
    )
    return list(rows.scalars())


async def set_branches(
    db: AsyncSession, actor: GeoScope, user_id: uuid.UUID, member_ids: list[uuid.UUID]
) -> list[UserBranchScope]:
    """Replaces the user's branches (caller commits). Changes go through the ORM (audited)."""
    await ensure_within_scope(db, actor, user_id=user_id)
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
    current = {branch.member_id: branch for branch in await branches_of(db, user_id)}
    for member_id, branch in current.items():
        if member_id not in wanted:
            await db.delete(branch)
    for member_id in wanted:
        if member_id not in current:
            db.add(UserBranchScope(user_id=user_id, member_id=member_id))
    await db.flush()
    return await branches_of(db, user_id)
