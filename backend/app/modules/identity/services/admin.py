"""User, grant and role administration (D-33, D-34, D-52, D-101)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.modules import permission_codes
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.identity import repository as repo
from app.modules.identity.models import (
    GrantOrigin,
    Role,
    RolePermission,
    User,
    UserStatus,
)
from app.modules.identity.services.access import (
    Access,
    ensure_can_assign,
    ensure_can_grant,
    load_access,
    utcnow,
)
from app.modules.identity.services.grants import (
    GrantView,
    ScopeSpec,
    add_grant,
    ensure_can_hand_out,
    grants_of,
    remove_grant,
    replace_scopes,
    scope_key,
    validate_scopes,
)
from app.modules.identity.services.scopes import (
    GeoScope,
    ensure_within_scope,
    manageable_users_filter,
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
    geo: GeoScope | None = None,
) -> CursorPage[UserView]:
    statement = select(User).where(repo.alive(User))
    scoped = manageable_users_filter(geo, col(User.id)) if geo else None
    if scoped is not None:
        statement = statement.where(scoped)
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


async def ensure_can_manage(
    db: AsyncSession, actor: Access, target_id: uuid.UUID, geo: GeoScope | None = None
) -> None:
    """Only a superadmin may act on a superadmin account, and only on users inside the actor's
    geographic scope (D-33, D-34)."""
    if not actor.grants_all and (await load_access(db, target_id)).grants_all:
        raise ForbiddenError("Solo un superadministrador puede gestionar esta cuenta.")
    if geo is not None:
        await ensure_within_scope(db, geo, user_id=target_id)


async def update_user(
    db: AsyncSession,
    *,
    actor: Access,
    user_id: uuid.UUID,
    full_name: str,
    geo: GeoScope | None = None,
) -> UserView:
    await ensure_can_manage(db, actor, user_id, geo)
    user = await _locked_user(db, user_id)
    user.full_name = full_name
    await db.commit()
    return await user_view(db, user_id)


async def disable_user(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor: Access,
    user_id: uuid.UUID,
    geo: GeoScope | None = None,
) -> UserView:
    if user_id == actor_id:
        raise ConflictError("No puedes desactivar tu propia cuenta.")
    await ensure_can_manage(db, actor, user_id, geo)
    user = await _locked_user(db, user_id)
    if (await load_access(db, user_id)).grants_all and await repo.count_active_superadmins(
        db, excluding=user_id
    ) == 0:
        raise ConflictError("No se puede desactivar al último superadministrador.")
    user.status = UserStatus.DISABLED
    await revoke_user_sessions(db, user_id, reason="user_disabled")
    await db.commit()
    return await user_view(db, user_id)


async def activate_user(
    db: AsyncSession, *, actor: Access, user_id: uuid.UUID, geo: GeoScope | None = None
) -> UserView:
    await ensure_can_manage(db, actor, user_id, geo)
    user = await _locked_user(db, user_id)
    if user.status != UserStatus.DISABLED:
        raise ConflictError("Solo se pueden reactivar cuentas desactivadas.")
    user.status = UserStatus.ACTIVE if user.password_hash else UserStatus.INVITED
    await db.commit()
    return await user_view(db, user_id)


async def unlock_user(
    db: AsyncSession, *, actor: Access, user_id: uuid.UUID, geo: GeoScope | None = None
) -> UserView:
    await ensure_can_manage(db, actor, user_id, geo)
    user = await _locked_user(db, user_id)
    user.locked_until = None
    user.failed_login_count = 0
    await db.commit()
    return await user_view(db, user_id)


@dataclass(frozen=True, slots=True)
class GrantRequest:
    """A wanted manual grant: `id` keeps an existing one (its scopes may change)."""

    role_id: uuid.UUID
    scopes: list[ScopeSpec]
    id: uuid.UUID | None = None


async def _plan_grants(
    db: AsyncSession,
    actor_id: uuid.UUID,
    actor: Access,
    manual: dict[uuid.UUID | None, GrantView],
    wanted: list[GrantRequest],
) -> tuple[
    list[tuple[Role, list[ScopeSpec]]], list[tuple[GrantView, list[ScopeSpec]]], list[GrantView]
]:
    """Validates the wanted grants against the current manual ones and checks that the actor
    can hand out everything that changes."""
    ids = [item.id for item in wanted if item.id is not None]
    if len(ids) != len(set(ids)):
        raise BadRequestError("Hay concesiones repetidas en la lista.")
    for grant_id in ids:
        if grant_id not in manual:
            raise BadRequestError(
                f"La concesión {grant_id} no existe o no es manual; las de un nombramiento "
                "se cambian desde el nombramiento."
            )
    roles = {role.id: role for role in await repo.roles_by_ids(db, [w.role_id for w in wanted])}
    if any(item.role_id not in roles for item in wanted):
        raise BadRequestError("Uno o más roles no existen.")

    plan_add: list[tuple[Role, list[ScopeSpec]]] = []
    plan_change: list[tuple[GrantView, list[ScopeSpec]]] = []
    for item in wanted:
        scopes = await validate_scopes(db, item.scopes)
        role = roles[item.role_id]
        if item.id is None:
            await ensure_can_hand_out(db, actor_id, actor, role, scopes)
            plan_add.append((role, scopes))
            continue
        view = manual[item.id]
        if view.role.id != item.role_id:
            raise BadRequestError(
                "No se cambia el rol de una concesión: quítala y agrega una nueva."
            )
        if set(scopes) != {scope_key(scope) for scope in view.scopes}:
            await ensure_can_hand_out(
                db, actor_id, actor, view.role, [scope_key(s) for s in view.scopes]
            )
            await ensure_can_hand_out(db, actor_id, actor, role, scopes)
            plan_change.append((view, scopes))
    removed = [view for gid, view in manual.items() if gid not in set(ids)]
    for view in removed:
        await ensure_can_hand_out(
            db, actor_id, actor, view.role, [scope_key(scope) for scope in view.scopes]
        )

    return plan_add, plan_change, removed


async def set_user_grants(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor: Access,
    user_id: uuid.UUID,
    wanted: list[GrantRequest],
    geo: GeoScope | None = None,
) -> list[GrantView]:
    """Replaces the user's manual grants. Grants from appointments are not touched here (they
    follow their appointment, D-104). Each added, changed or removed grant needs the actor to
    be able to hand it out (D-101)."""
    await ensure_can_manage(db, actor, user_id, geo)
    await _locked_user(db, user_id)
    current = {view.grant.id: view for view in await grants_of(db, user_id)}
    manual = {gid: view for gid, view in current.items() if view.grant.origin == GrantOrigin.MANUAL}

    plan_add, plan_change, removed = await _plan_grants(db, actor_id, actor, manual, wanted)

    kept_superadmin = any(
        view.role.grants_all for gid, view in current.items() if view not in removed
    ) or any(role.grants_all for role, _ in plan_add)
    if (
        any(view.role.grants_all for view in removed)
        and not kept_superadmin
        and await repo.count_active_superadmins(db, excluding=user_id) == 0
    ):
        raise ConflictError("No se puede quitar el rol al último superadministrador.")

    for view in removed:
        await remove_grant(db, view.grant)
    for view, scopes in plan_change:
        await replace_scopes(db, view.grant, scopes)
    for role, scopes in plan_add:
        await add_grant(db, user_id=user_id, role=role, scopes=scopes, assigned_by=actor_id)
    await db.commit()
    return await grants_of(db, user_id)


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
            "permissions": sorted(permission_codes()) if role.grants_all else self.permissions,
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
    unknown = set(unique) - permission_codes()
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
