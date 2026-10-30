"""/users, /roles, /permissions — administration (RBAC, grants and scope; D-33, D-34, D-101)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.core.db.session import SessionDep
from app.core.errors import ConflictError, ForbiddenError
from app.core.mail import send_safely
from app.core.pagination import CursorPage, PageParams, page_params
from app.modules.identity import repository as repo
from app.modules.identity.container import ServicesDep
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.models import UserStatus
from app.modules.identity.permissions import Perm
from app.modules.identity.schemas import (
    GrantOut,
    GrantsRequest,
    PermissionOut,
    RevokedCount,
    RoleCreateRequest,
    RoleOut,
    RolePermissionsRequest,
    RoleUpdateRequest,
    SessionOut,
    UserInvitedResponse,
    UserInviteRequest,
    UserOut,
    UserUpdateRequest,
)
from app.modules.identity.services import admin, credentials, mfa, sessions
from app.modules.identity.services.access import utcnow
from app.modules.identity.services.grants import GrantView, grants_of
from app.modules.identity.services.scopes import ensure_within_scope

users_router = APIRouter(prefix="/users", tags=["users"])
roles_router = APIRouter(tags=["roles"])

UserReader = Annotated[CurrentUser, permission(Perm.USER_READ)]
UserCreator = Annotated[CurrentUser, permission(Perm.USER_CREATE)]
UserEditor = Annotated[CurrentUser, permission(Perm.USER_UPDATE)]
UserDisabler = Annotated[CurrentUser, permission(Perm.USER_DISABLE)]
RoleAssigner = Annotated[CurrentUser, permission(Perm.USER_ASSIGN_ROLES)]
MfaResetter = Annotated[CurrentUser, permission(Perm.USER_RESET_MFA)]
SessionRevoker = Annotated[CurrentUser, permission(Perm.USER_REVOKE_SESSIONS)]
RoleReader = Annotated[CurrentUser, permission(Perm.ROLE_READ)]
RoleCreator = Annotated[CurrentUser, permission(Perm.ROLE_CREATE)]
RoleEditor = Annotated[CurrentUser, permission(Perm.ROLE_UPDATE)]
RoleDeleter = Annotated[CurrentUser, permission(Perm.ROLE_DELETE)]
PermissionReader = Annotated[CurrentUser, permission(Perm.PERMISSION_READ)]


def _user_out(view: admin.UserView) -> UserOut:
    return UserOut.model_validate(view.payload)


# --- users -------------------------------------------------------------------------------


@users_router.get("", operation_id="listUsers", summary="Listar usuarios")
async def list_users(
    db: SessionDep,
    actor: UserReader,
    params: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
    q: Annotated[
        str | None, Query(min_length=2, max_length=100, description="Correo o nombre")
    ] = None,
    role_id: uuid.UUID | None = None,
) -> CursorPage[UserOut]:
    page = await admin.list_users(
        db, params, status=status_filter, search=q, role_id=role_id, geo=actor.geo
    )
    return CursorPage[UserOut](
        items=[_user_out(view) for view in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@users_router.post(
    "",
    operation_id="inviteUser",
    status_code=status.HTTP_201_CREATED,
    summary="Invitar a un usuario (envía correo)",
)
async def invite_user(
    body: UserInviteRequest,
    background: BackgroundTasks,
    db: SessionDep,
    services: ServicesDep,
    actor: UserCreator,
) -> UserInvitedResponse:
    user, invitation, email = await credentials.invite_user(
        db,
        services,
        actor_id=actor.id,
        actor=actor.access,
        email=body.email,
        full_name=body.full_name,
        role_ids=body.role_ids,
    )
    background.add_task(send_safely, services.mailer, email)
    assert user.id is not None  # noqa: S101
    view = await admin.user_view(db, user.id)
    return UserInvitedResponse.model_validate(
        {**view.payload, "invitation_expires_at": invitation.expires_at}
    )


@users_router.get("/{user_id}", operation_id="getUser", summary="Detalle de un usuario")
async def get_user(user_id: uuid.UUID, db: SessionDep, actor: UserReader) -> UserOut:
    view = await admin.user_view(db, user_id)
    await ensure_within_scope(db, actor.geo, user_id=user_id)
    return _user_out(view)


@users_router.patch("/{user_id}", operation_id="updateUser", summary="Editar datos de un usuario")
async def update_user(
    user_id: uuid.UUID, body: UserUpdateRequest, db: SessionDep, actor: UserEditor
) -> UserOut:
    return _user_out(
        await admin.update_user(
            db, actor=actor.access, user_id=user_id, full_name=body.full_name, geo=actor.geo
        )
    )


@users_router.post(
    "/{user_id}/disable", operation_id="disableUser", summary="Desactivar (cierra sesiones)"
)
async def disable_user(user_id: uuid.UUID, db: SessionDep, actor: UserDisabler) -> UserOut:
    return _user_out(
        await admin.disable_user(
            db, actor_id=actor.id, actor=actor.access, user_id=user_id, geo=actor.geo
        )
    )


@users_router.post("/{user_id}/activate", operation_id="activateUser", summary="Reactivar")
async def activate_user(user_id: uuid.UUID, db: SessionDep, actor: UserDisabler) -> UserOut:
    return _user_out(
        await admin.activate_user(db, actor=actor.access, user_id=user_id, geo=actor.geo)
    )


@users_router.post(
    "/{user_id}/unlock", operation_id="unlockUser", summary="Desbloquear tras intentos fallidos"
)
async def unlock_user(user_id: uuid.UUID, db: SessionDep, actor: UserDisabler) -> UserOut:
    return _user_out(
        await admin.unlock_user(db, actor=actor.access, user_id=user_id, geo=actor.geo)
    )


@users_router.post(
    "/{user_id}/invitation", operation_id="resendInvitation", summary="Reenviar la invitación"
)
async def resend_invitation(
    user_id: uuid.UUID,
    background: BackgroundTasks,
    db: SessionDep,
    services: ServicesDep,
    actor: UserCreator,
) -> UserInvitedResponse:
    await admin.ensure_can_manage(db, actor.access, user_id, actor.geo)
    _, invitation, email = await credentials.resend_invitation(
        db, services, actor_id=actor.id, user_id=user_id
    )
    background.add_task(send_safely, services.mailer, email)
    view = await admin.user_view(db, user_id)
    return UserInvitedResponse.model_validate(
        {**view.payload, "invitation_expires_at": invitation.expires_at}
    )


@users_router.post(
    "/{user_id}/mfa/reset",
    operation_id="resetUserMfa",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restablecer el segundo factor (cierra sus sesiones)",
)
async def reset_user_mfa(user_id: uuid.UUID, db: SessionDep, actor: MfaResetter) -> None:
    if user_id == actor.id:
        raise ConflictError("No puedes restablecer tu propio segundo factor desde aquí.")
    await admin.ensure_can_manage(db, actor.access, user_id, actor.geo)
    await mfa.admin_reset_mfa(db, target_id=user_id)


@users_router.get(
    "/{user_id}/sessions", operation_id="listUserSessions", summary="Sesiones activas"
)
async def list_user_sessions(
    user_id: uuid.UUID, db: SessionDep, actor: SessionRevoker
) -> list[SessionOut]:
    await admin.user_view(db, user_id)  # 404 if missing
    await ensure_within_scope(db, actor.geo, user_id=user_id)
    return [SessionOut.model_validate(s) for s in await repo.active_sessions(db, user_id, utcnow())]


@users_router.post(
    "/{user_id}/sessions/revoke",
    operation_id="revokeUserSessions",
    summary="Cerrar todas sus sesiones",
)
async def revoke_user_sessions(
    user_id: uuid.UUID, db: SessionDep, actor: SessionRevoker
) -> RevokedCount:
    await admin.ensure_can_manage(db, actor.access, user_id, actor.geo)
    count = await sessions.revoke_user_sessions(db, user_id, reason="revoked_by_admin")
    await db.commit()
    return RevokedCount(revoked=count)


def _grant_out(view: GrantView) -> GrantOut:
    return GrantOut.from_parts(view.grant, view.role, view.scopes)


@users_router.get(
    "/{user_id}/grants", operation_id="listUserGrants", summary="Concesiones (rol y alcance)"
)
async def list_user_grants(user_id: uuid.UUID, db: SessionDep, actor: UserReader) -> list[GrantOut]:
    await admin.user_view(db, user_id)
    await ensure_within_scope(db, actor.geo, user_id=user_id)
    return [_grant_out(view) for view in await grants_of(db, user_id)]


@users_router.put(
    "/{user_id}/grants",
    operation_id="setUserGrants",
    summary="Reemplazar las concesiones manuales",
    description=(
        "Cada concesión es un rol con su alcance: sus permisos solo valen dentro de ese alcance "
        "(D-101). Las concesiones de un nombramiento no se tocan aquí. No se puede conceder un "
        "rol con permisos que no tienes ni un alcance mayor al que tienes para esos permisos."
    ),
)
async def set_user_grants(
    user_id: uuid.UUID, body: GrantsRequest, db: SessionDep, actor: RoleAssigner
) -> list[GrantOut]:
    if not actor.has(Perm.USER_ASSIGN_SCOPES):
        raise ForbiddenError(f"No tienes el permiso «{Perm.USER_ASSIGN_SCOPES}».")
    views = await admin.set_user_grants(
        db,
        actor_id=actor.id,
        actor=actor.access,
        user_id=user_id,
        wanted=[
            admin.GrantRequest(
                id=item.id,
                role_id=item.role_id,
                scopes=[(scope.level, scope.node_id) for scope in item.scopes],
            )
            for item in body.grants
        ],
        geo=actor.geo,
    )
    return [_grant_out(view) for view in views]


# --- roles & permissions -------------------------------------------------------------------


def _role_out(view: admin.RoleView) -> RoleOut:
    return RoleOut.model_validate(view.payload)


@roles_router.get("/roles", operation_id="listRoles", summary="Listar roles")
async def list_roles(db: SessionDep, _: RoleReader) -> list[RoleOut]:
    return [_role_out(view) for view in await admin.list_roles(db)]


@roles_router.post(
    "/roles", operation_id="createRole", status_code=status.HTTP_201_CREATED, summary="Crear un rol"
)
async def create_role(body: RoleCreateRequest, db: SessionDep, actor: RoleCreator) -> RoleOut:
    return _role_out(
        await admin.create_role(
            db,
            actor=actor.access,
            code=body.code,
            name=body.name,
            description=body.description,
            requires_mfa=body.requires_mfa,
            permissions=body.permissions,
        )
    )


@roles_router.get("/roles/{role_id}", operation_id="getRole", summary="Detalle de un rol")
async def get_role(role_id: uuid.UUID, db: SessionDep, _: RoleReader) -> RoleOut:
    return _role_out(await admin.role_view(db, role_id))


@roles_router.patch("/roles/{role_id}", operation_id="updateRole", summary="Editar un rol")
async def update_role(
    role_id: uuid.UUID, body: RoleUpdateRequest, db: SessionDep, actor: RoleEditor
) -> RoleOut:
    return _role_out(
        await admin.update_role(
            db,
            actor=actor.access,
            role_id=role_id,
            name=body.name,
            description=body.description,
            requires_mfa=body.requires_mfa,
        )
    )


@roles_router.put(
    "/roles/{role_id}/permissions", operation_id="setRolePermissions", summary="Reemplazar permisos"
)
async def set_role_permissions(
    role_id: uuid.UUID, body: RolePermissionsRequest, db: SessionDep, actor: RoleEditor
) -> RoleOut:
    return _role_out(
        await admin.set_role_permissions(
            db, actor=actor.access, role_id=role_id, permissions=body.permissions
        )
    )


@roles_router.delete(
    "/roles/{role_id}",
    operation_id="deleteRole",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un rol sin usuarios",
)
async def delete_role(role_id: uuid.UUID, db: SessionDep, actor: RoleDeleter) -> None:
    await admin.delete_role(db, actor=actor.access, role_id=role_id)


@roles_router.get("/permissions", operation_id="listPermissions", summary="Catálogo de permisos")
async def list_permissions(db: SessionDep, _: PermissionReader) -> list[PermissionOut]:
    return [PermissionOut.model_validate(p) for p in await repo.all_permissions(db)]
