"""Data access for identity. Queries only; transactions and rules live in services.

Columns are wrapped with ``col()`` so SQLModel attributes type-check as SQL expressions.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, Exists, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.modules.identity.models import (
    Permission,
    RecoveryCode,
    RefreshToken,
    Role,
    RolePermission,
    TotpCredential,
    User,
    UserInvitation,
    UserRole,
    UserSession,
    UserStatus,
)


def alive(model: type[User] | type[Role] | type[Permission]) -> ColumnElement[bool]:
    return col(model.deleted_at).is_(None)


async def user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(col(User.email) == email, alive(User)))
    return result.scalar_one_or_none()


async def user_by_id(
    db: AsyncSession, user_id: uuid.UUID, *, for_update: bool = False
) -> User | None:
    statement = select(User).where(col(User.id) == user_id, alive(User))
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def roles_of(db: AsyncSession, user_id: uuid.UUID) -> list[Role]:
    result = await db.execute(
        select(Role)
        .join(UserRole, col(UserRole.role_id) == col(Role.id))
        .where(col(UserRole.user_id) == user_id, alive(Role))
        .order_by(col(Role.name))
    )
    return list(result.scalars())


async def roles_by_user(
    db: AsyncSession, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Role]]:
    grouped: dict[uuid.UUID, list[Role]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return grouped
    result = await db.execute(
        select(col(UserRole.user_id), Role)
        .join(Role, col(UserRole.role_id) == col(Role.id))
        .where(col(UserRole.user_id).in_(user_ids), alive(Role))
        .order_by(col(Role.name))
    )
    for user_id, role in result.all():
        grouped[user_id].append(role)
    return grouped


async def permission_codes_of(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    result = await db.execute(
        select(col(Permission.code))
        .join(RolePermission, col(RolePermission.permission_id) == col(Permission.id))
        .join(UserRole, col(UserRole.role_id) == col(RolePermission.role_id))
        .join(Role, col(Role.id) == col(UserRole.role_id))
        .where(col(UserRole.user_id) == user_id, alive(Role), alive(Permission))
    )
    return set(result.scalars())


async def permission_codes_of_role(db: AsyncSession, role_id: uuid.UUID) -> set[str]:
    result = await db.execute(
        select(col(Permission.code))
        .join(RolePermission, col(RolePermission.permission_id) == col(Permission.id))
        .where(col(RolePermission.role_id) == role_id, alive(Permission))
    )
    return set(result.scalars())


async def permissions_by_codes(db: AsyncSession, codes: Sequence[str]) -> list[Permission]:
    if not codes:
        return []
    result = await db.execute(
        select(Permission).where(col(Permission.code).in_(codes), alive(Permission))
    )
    return list(result.scalars())


async def all_permissions(db: AsyncSession) -> list[Permission]:
    result = await db.execute(
        select(Permission).where(alive(Permission)).order_by(col(Permission.code))
    )
    return list(result.scalars())


async def roles_by_ids(db: AsyncSession, role_ids: Sequence[uuid.UUID]) -> list[Role]:
    if not role_ids:
        return []
    result = await db.execute(select(Role).where(col(Role.id).in_(role_ids), alive(Role)))
    return list(result.scalars())


async def role_by_id(db: AsyncSession, role_id: uuid.UUID) -> Role | None:
    result = await db.execute(select(Role).where(col(Role.id) == role_id, alive(Role)))
    return result.scalar_one_or_none()


async def role_by_code(db: AsyncSession, code: str) -> Role | None:
    result = await db.execute(select(Role).where(col(Role.code) == code, alive(Role)))
    return result.scalar_one_or_none()


async def all_roles(db: AsyncSession) -> list[Role]:
    result = await db.execute(select(Role).where(alive(Role)).order_by(col(Role.name)))
    return list(result.scalars())


async def role_permission_map(db: AsyncSession) -> dict[uuid.UUID, list[str]]:
    result = await db.execute(
        select(col(RolePermission.role_id), col(Permission.code))
        .join(Permission, col(Permission.id) == col(RolePermission.permission_id))
        .where(alive(Permission))
        .order_by(col(Permission.code))
    )
    grouped: dict[uuid.UUID, list[str]] = {}
    for role_id, code in result.all():
        grouped.setdefault(role_id, []).append(code)
    return grouped


async def role_user_counts(db: AsyncSession) -> dict[uuid.UUID, int]:
    result = await db.execute(
        select(col(UserRole.role_id), func.count())
        .join(User, col(User.id) == col(UserRole.user_id))
        .where(alive(User))
        .group_by(col(UserRole.role_id))
    )
    return {role_id: int(count) for role_id, count in result.all()}


async def count_active_superadmins(db: AsyncSession, *, excluding: uuid.UUID | None = None) -> int:
    statement = (
        select(func.count(func.distinct(col(User.id))))
        .join(UserRole, col(UserRole.user_id) == col(User.id))
        .join(Role, col(Role.id) == col(UserRole.role_id))
        .where(
            col(Role.grants_all).is_(True),
            alive(Role),
            alive(User),
            col(User.status) == UserStatus.ACTIVE,
        )
    )
    if excluding is not None:
        statement = statement.where(col(User.id) != excluding)
    return int((await db.execute(statement)).scalar_one())


async def totp_of(
    db: AsyncSession, user_id: uuid.UUID, *, for_update: bool = False
) -> TotpCredential | None:
    statement = select(TotpCredential).where(col(TotpCredential.user_id) == user_id)
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def confirmed_totp_user_ids(
    db: AsyncSession, user_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    if not user_ids:
        return set()
    result = await db.execute(
        select(col(TotpCredential.user_id)).where(
            col(TotpCredential.user_id).in_(user_ids),
            col(TotpCredential.confirmed_at).is_not(None),
        )
    )
    return set(result.scalars())


async def unused_recovery_codes(db: AsyncSession, user_id: uuid.UUID) -> list[RecoveryCode]:
    result = await db.execute(
        select(RecoveryCode)
        .where(col(RecoveryCode.user_id) == user_id, col(RecoveryCode.used_at).is_(None))
        .with_for_update()
    )
    return list(result.scalars())


async def refresh_token_by_hash(db: AsyncSession, token_hash: bytes) -> RefreshToken | None:
    result = await db.execute(
        select(RefreshToken).where(col(RefreshToken.token_hash) == token_hash).with_for_update()
    )
    return result.scalar_one_or_none()


async def session_by_id(
    db: AsyncSession, session_id: uuid.UUID, *, for_update: bool = False
) -> UserSession | None:
    statement = select(UserSession).where(col(UserSession.id) == session_id)
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def active_sessions(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> list[UserSession]:
    result = await db.execute(
        select(UserSession)
        .where(
            col(UserSession.user_id) == user_id,
            col(UserSession.revoked_at).is_(None),
            col(UserSession.expires_at) > now,
        )
        .order_by(
            col(UserSession.last_seen_at).desc().nulls_last(), col(UserSession.created_at).desc()
        )
    )
    return list(result.scalars())


async def revoke_session_tokens(
    db: AsyncSession, session_ids: Sequence[uuid.UUID], now: datetime
) -> None:
    """Bulk revocation of refresh tokens (refresh tokens are not audited row by row, D-48)."""
    if session_ids:
        await db.execute(
            update(RefreshToken)
            .where(
                col(RefreshToken.session_id).in_(session_ids),
                col(RefreshToken.revoked_at).is_(None),
            )
            .values(revoked_at=now)
        )


async def pending_invitations(db: AsyncSession, user_id: uuid.UUID) -> list[UserInvitation]:
    result = await db.execute(
        select(UserInvitation).where(
            col(UserInvitation.user_id) == user_id,
            col(UserInvitation.accepted_at).is_(None),
            col(UserInvitation.revoked_at).is_(None),
        )
    )
    return list(result.scalars())


async def invitation_by_hash(db: AsyncSession, token_hash: bytes) -> UserInvitation | None:
    result = await db.execute(
        select(UserInvitation).where(col(UserInvitation.token_hash) == token_hash).with_for_update()
    )
    return result.scalar_one_or_none()


def user_search_filter(term: str) -> ColumnElement[bool]:
    pattern = f"%{term.strip()}%"
    return or_(col(User.email).ilike(pattern), col(User.full_name).ilike(pattern))


def user_has_role(role_id: uuid.UUID) -> Exists:
    return exists().where(col(UserRole.user_id) == col(User.id), col(UserRole.role_id) == role_id)
