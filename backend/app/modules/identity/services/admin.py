"""User and role administration. Geographic scope filtering arrives in phase C (D-42)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.identity import repository as repo
from app.modules.identity.models import Role, RolePermission, User, UserRole, UserStatus
from app.modules.identity.permissions import PERMISSIONS
from app.modules.identity.services.access import (
    Access,
    ensure_can_assign,
    ensure_can_grant,
    load_access,
    utcnow,
)
from app.modules.identity.services.sessions import revoke_user_sessions

# --- read models -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserView:
    user: User
    roles: list[Role]
    mfa_enabled: bool

    @property
    def payload(self) -> dict[str, object]:
        user = self.user
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "status": user.status,
            "roles": self.roles,
            "mfa_enabled": self.mfa_enabled,
            "locked_until": user.locked_until
            if user.locked_until and user.locked_until > utcnow()
            else None,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
        }


async def _views(db: AsyncSession, users: list[User]) -> list[UserView]:
    ids = [user.id for user in users if user.id is not None]
    roles = await repo.roles_by_user(db, ids)
    with_mfa = await repo.confirmed_totp_user_ids(db, ids)
    views = []
    for user in users:
        assert user.id is not None  # noqa: S101
        views.append(UserView(user=user, roles=roles[user.id], mfa_enabled=user.id in with_mfa))
    return views


async def user_view(db: AsyncSession, user_id: uuid.UUID) -> UserView:
    user = await repo.user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")
    return (await _views(db, [user]))[0]


async def list_users(
    db: AsyncSession,
    params: PageParams,
    *,
    status: UserStatus | None,
    search: str | None,
    role_id: uuid.UUID | None,
) -> CursorPage[UserView]:
    statement = select(User).where(repo.alive(User))
    if status is not None:
        statement = statement.where(col(User.status) == status)
    if search:
        statement = statement.where(repo.user_search_filter(search))
    if role_id is not None:
        statement = statement.where(repo.user_has_role(role_id))
    sort = parse_sort(
        params.sort,
        allowed={
            "email": col(User.email),
            "full_name": col(User.full_name),
            "created_at": col(User.created_at),
            "last_login_at": col(User.last_login_at),
        },
        tiebreaker=col(User.id),
        default="full_name",
    )
    page: CursorPage[User] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return CursorPage[UserView](
        items=await _views(db, page.items),
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


# --- user mutations ----------------------------------------------------------------------


async def _locked_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await repo.user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")
    return user


async def ensure_can_manage(db: AsyncSession, actor: Access, target_id: uuid.UUID) -> None:
    """Only a superadmin may act on a superadmin account."""
    if not actor.grants_all and (await load_access(db, target_id)).grants_all:
        raise ForbiddenError("Solo un superadministrador puede gestionar esta cuenta.")


async def update_user(
    db: AsyncSession, *, actor: Access, user_id: uuid.UUID, full_name: str
) -> UserView:
    await ensure_can_manage(db, actor, user_id)
    user = await _locked_user(db, user_id)
    user.full_name = full_name
    await db.commit()
    return await user_view(db, user_id)


async def disable_user(
    db: AsyncSession, *, actor_id: uuid.UUID, actor: Access, user_id: uuid.UUID
) -> UserView:
    if user_id == actor_id:
        raise ConflictError("No puedes desactivar tu propia cuenta.")
    await ensure_can_manage(db, actor, user_id)
    user = await _locked_user(db, user_id)
    if (await load_access(db, user_id)).grants_all and await repo.count_active_superadmins(
        db, excluding=user_id
    ) == 0:
        raise ConflictError("No se puede desactivar al último superadministrador.")
    user.status = UserStatus.DISABLED
    await revoke_user_sessions(db, user_id, reason="user_disabled")
    await db.commit()
    return await user_view(db, user_id)


async def activate_user(db: AsyncSession, *, actor: Access, user_id: uuid.UUID) -> UserView:
    await ensure_can_manage(db, actor, user_id)
    user = await _locked_user(db, user_id)
    if user.status != UserStatus.DISABLED:
        raise ConflictError("Solo se pueden reactivar cuentas desactivadas.")
    user.status = UserStatus.ACTIVE if user.password_hash else UserStatus.INVITED
    await db.commit()
    return await user_view(db, user_id)


async def unlock_user(db: AsyncSession, *, actor: Access, user_id: uuid.UUID) -> UserView:
    await ensure_can_manage(db, actor, user_id)
    user = await _locked_user(db, user_id)
    user.locked_until = None
    user.failed_login_count = 0
    await db.commit()
    return await user_view(db, user_id)


async def set_user_roles(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor: Access,
    user_id: uuid.UUID,
    role_ids: list[uuid.UUID],
) -> UserView:
    await ensure_can_manage(db, actor, user_id)
    await _locked_user(db, user_id)
    wanted = await repo.roles_by_ids(db, role_ids)
    if len(wanted) != len(set(role_ids)):
        raise BadRequestError("Uno o más roles no existen.")
    current = await repo.roles_of(db, user_id)
    added = [role for role in wanted if role.id not in {r.id for r in current}]
    removed = [role for role in current if role.id not in {r.id for r in wanted}]
    await ensure_can_assign(db, actor, [*added, *removed])

    removes_superadmin = any(r.grants_all for r in removed) and not any(
        r.grants_all for r in wanted
    )
    if removes_superadmin and await repo.count_active_superadmins(db, excluding=user_id) == 0:
        raise ConflictError("No se puede quitar el rol al último superadministrador.")

    for role in removed:
        link = await db.get(UserRole, (user_id, role.id))
        if link is not None:
            await db.delete(link)
    for role in added:
        assert role.id is not None  # noqa: S101
        db.add(UserRole(user_id=user_id, role_id=role.id, assigned_by_user_id=actor_id))
    await db.commit()
    return await user_view(db, user_id)


# --- roles -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoleView:
    role: Role
    permissions: list[str]
    user_count: int

    @property
    def payload(self) -> dict[str, object]:
        role = self.role
        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "requires_mfa": role.requires_mfa,
            "is_system": role.is_system,
            "grants_all": role.grants_all,
            "permissions": sorted(PERMISSIONS) if role.grants_all else self.permissions,
            "user_count": self.user_count,
        }


async def list_roles(db: AsyncSession) -> list[RoleView]:
    roles = await repo.all_roles(db)
    permissions = await repo.role_permission_map(db)
    counts = await repo.role_user_counts(db)
    return [
        RoleView(
            role=role,
            permissions=permissions.get(pk(role), []),
            user_count=counts.get(pk(role), 0),
        )
        for role in roles
    ]


async def role_view(db: AsyncSession, role_id: uuid.UUID) -> RoleView:
    for view in await list_roles(db):
        if view.role.id == role_id:
            return view
    raise NotFoundError("Rol no encontrado.")


async def _validated_permissions(
    db: AsyncSession, actor: Access, codes: list[str]
) -> list[uuid.UUID]:
    unique = sorted(set(codes))
    unknown = set(unique) - PERMISSIONS
    if unknown:
        raise BadRequestError("Permisos inexistentes: " + ", ".join(sorted(unknown)) + ".")
    ensure_can_grant(actor, unique)
    return [pk(permission) for permission in await repo.permissions_by_codes(db, unique)]


async def create_role(
    db: AsyncSession,
    *,
    actor: Access,
    code: str,
    name: str,
    description: str | None,
    requires_mfa: bool,
    permissions: list[str],
) -> RoleView:
    if await repo.role_by_code(db, code) is not None:
        raise ConflictError("Ya existe un rol con ese código.")
    permission_ids = await _validated_permissions(db, actor, permissions)
    role = Role(code=code, name=name, description=description, requires_mfa=requires_mfa)
    db.add(role)
    await db.flush()
    assert role.id is not None  # noqa: S101
    for permission_id in permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=permission_id))
    await db.commit()
    return await role_view(db, role.id)


async def _editable_role(db: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await repo.role_by_id(db, role_id)
    if role is None:
        raise NotFoundError("Rol no encontrado.")
    if role.grants_all:
        raise ConflictError("El rol de superadministrador no se puede modificar.")
    return role


async def update_role(
    db: AsyncSession,
    *,
    actor: Access,
    role_id: uuid.UUID,
    name: str | None,
    description: str | None,
    requires_mfa: bool | None,
) -> RoleView:
    role = await _editable_role(db, role_id)
    await ensure_can_assign(db, actor, [role])
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if requires_mfa is not None:
        role.requires_mfa = requires_mfa
    await db.commit()
    return await role_view(db, role_id)


async def set_role_permissions(
    db: AsyncSession, *, actor: Access, role_id: uuid.UUID, permissions: list[str]
) -> RoleView:
    role = await _editable_role(db, role_id)
    await ensure_can_assign(db, actor, [role])  # cannot edit a role more powerful than oneself
    wanted = set(await _validated_permissions(db, actor, permissions))
    links = (
        await db.execute(select(RolePermission).where(col(RolePermission.role_id) == role_id))
    ).scalars()
    current = {link.permission_id: link for link in links}
    for permission_id, link in current.items():
        if permission_id not in wanted:
            await db.delete(link)
    for permission_id in wanted - set(current):
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))
    await db.commit()
    return await role_view(db, role_id)


async def delete_role(db: AsyncSession, *, actor: Access, role_id: uuid.UUID) -> None:
    role = await _editable_role(db, role_id)
    if role.is_system:
        raise ConflictError("Los roles del sistema no se pueden eliminar.")
    await ensure_can_assign(db, actor, [role])
    if (await repo.role_user_counts(db)).get(role_id, 0):
        raise ConflictError("El rol tiene usuarios asignados; retíralos antes de eliminarlo.")
    role.deleted_at = utcnow()
    await db.commit()
