"""/auth: login, second factor, refresh, logout, profile, password, invitations, own sessions.

The access token travels in the Authorization header (kept in memory by the panel); the
refresh token only in an httpOnly + Secure + SameSite=Strict cookie scoped to /api/v1/auth.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.core.db.session import SessionDep
from app.core.errors import ForbiddenError, NotFoundError
from app.core.mail import send_safely
from app.modules.identity import repository as repo
from app.modules.identity.container import IdentityServices, ServicesDep
from app.modules.identity.dependencies import AnyScopeUserDep, CurrentUserDep
from app.modules.identity.models import UserStatus
from app.modules.identity.schemas import (
    AuthenticatedResponse,
    GrantOut,
    InvitationAcceptRequest,
    InvitationInfo,
    InvitationTokenRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MfaRequiredResponse,
    MfaStatus,
    MfaVerifyRequest,
    PasswordChangeRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    RecoveryCodesRequest,
    RecoveryCodesResponse,
    RevokedCount,
    RoleSummary,
    SessionOut,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpDisableRequest,
    TotpSetupResponse,
)
from app.modules.identity.services import auth as auth_service
from app.modules.identity.services import credentials, mfa, sessions
from app.modules.identity.services.access import utcnow
from app.modules.identity.services.auth import MfaChallenge
from app.modules.identity.services.grants import grants_of
from app.modules.identity.services.sessions import InvalidRefreshError, IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, services: IdentityServices, token: str) -> None:
    settings = services.settings
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=settings.refresh_token_ttl_seconds,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, services: IdentityServices) -> None:
    settings = services.settings
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _authenticated(
    response: Response, services: IdentityServices, issued: IssuedSession
) -> AuthenticatedResponse:
    _set_refresh_cookie(response, services, issued.refresh_token)
    return AuthenticatedResponse(
        access_token=issued.access_token, expires_in=issued.expires_in, scope=issued.scope
    )


def _check_origin(request: Request, services: IdentityServices) -> None:
    """Defense in depth for cookie-authenticated endpoints (besides SameSite=Strict)."""
    origin = request.headers.get("origin")
    if origin and origin not in services.settings.cors_allowed_origins:
        raise ForbiddenError("Origen no permitido.")


# --- authentication ----------------------------------------------------------------------


@router.post("/login", operation_id="login", summary="Iniciar sesión con correo y contraseña")
async def login(
    body: LoginRequest, response: Response, db: SessionDep, services: ServicesDep
) -> LoginResponse:
    result = await auth_service.login(
        db, services, email=body.email, password=body.password, device_label=body.device_label
    )
    if isinstance(result, MfaChallenge):
        return MfaRequiredResponse(mfa_token=result.mfa_token, expires_in=result.expires_in)
    return _authenticated(response, services, result)


@router.post(
    "/mfa/verify", operation_id="verifyMfa", summary="Completar el inicio de sesión con TOTP"
)
async def verify_mfa(
    body: MfaVerifyRequest, response: Response, db: SessionDep, services: ServicesDep
) -> AuthenticatedResponse:
    issued = await auth_service.verify_mfa(
        db,
        services,
        mfa_token=body.mfa_token,
        code=body.code,
        recovery_code=body.recovery_code,
        device_label=body.device_label,
    )
    return _authenticated(response, services, issued)


@router.post("/refresh", operation_id="refreshSession", summary="Renovar el access token")
async def refresh(
    request: Request,
    response: Response,
    db: SessionDep,
    services: ServicesDep,
) -> AuthenticatedResponse:
    _check_origin(request, services)
    token = request.cookies.get(services.settings.refresh_cookie_name)
    if not token:
        raise InvalidRefreshError("No hay una sesión activa.")
    try:
        issued = await sessions.refresh(db, services, token)
    except InvalidRefreshError:
        _clear_refresh_cookie(response, services)
        raise
    return _authenticated(response, services, issued)


@router.post(
    "/logout",
    operation_id="logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
)
async def logout(
    response: Response, user: AnyScopeUserDep, db: SessionDep, services: ServicesDep
) -> None:
    await auth_service.logout(db, user.session_id)
    _clear_refresh_cookie(response, services)


@router.get("/me", operation_id="getMe", summary="Perfil, roles y permisos del usuario actual")
async def me(user: AnyScopeUserDep, db: SessionDep) -> MeResponse:
    credential = await repo.totp_of(db, user.id)
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        status=UserStatus.ACTIVE,
        roles=[RoleSummary.model_validate(role) for role in user.access.roles],
        permissions=user.access.effective_permissions(),
        grants_all=user.access.grants_all,
        mfa=MfaStatus(
            enabled=credential is not None and credential.confirmed_at is not None,
            required=user.access.requires_mfa,
        ),
        session_id=user.session_id,
        scope=user.scope,
        geo_unrestricted=user.geo.unrestricted,
        grants=[
            GrantOut.from_parts(v.grant, v.role, v.scopes) for v in await grants_of(db, user.id)
        ],
    )


# --- passwords & invitations ---------------------------------------------------------------


@router.post(
    "/password/change",
    operation_id="changePassword",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la contraseña (cierra las demás sesiones)",
)
async def change_password(
    body: PasswordChangeRequest, user: CurrentUserDep, db: SessionDep, services: ServicesDep
) -> None:
    await credentials.change_password(
        db,
        services,
        user_id=user.id,
        current_session_id=user.session_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )


@router.post(
    "/password/forgot",
    operation_id="forgotPassword",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Solicitar enlace para restablecer la contraseña",
)
async def forgot_password(
    body: PasswordForgotRequest, background: BackgroundTasks, db: SessionDep, services: ServicesDep
) -> None:
    email = await credentials.request_password_reset(db, services, email=body.email)
    if email is not None:
        background.add_task(send_safely, services.mailer, email)


@router.post(
    "/password/reset",
    operation_id="resetPassword",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restablecer la contraseña con el enlace recibido",
)
async def reset_password(body: PasswordResetRequest, db: SessionDep, services: ServicesDep) -> None:
    await credentials.reset_password(db, services, token=body.token, new_password=body.new_password)


@router.post(
    "/invitations/inspect", operation_id="inspectInvitation", summary="Validar una invitación"
)
async def inspect_invitation(body: InvitationTokenRequest, db: SessionDep) -> InvitationInfo:
    email, full_name, expires_at = await credentials.inspect_invitation(db, token=body.token)
    return InvitationInfo(email=email, full_name=full_name, expires_at=expires_at)


@router.post(
    "/invitations/accept",
    operation_id="acceptInvitation",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Aceptar una invitación y definir la contraseña",
)
async def accept_invitation(
    body: InvitationAcceptRequest, db: SessionDep, services: ServicesDep
) -> None:
    await credentials.accept_invitation(
        db, services, token=body.token, password=body.password, full_name=body.full_name
    )


# --- second factor -------------------------------------------------------------------------


@router.post("/mfa/totp/setup", operation_id="setupTotp", summary="Iniciar el enrolamiento TOTP")
async def setup_totp(
    user: AnyScopeUserDep, db: SessionDep, services: ServicesDep
) -> TotpSetupResponse:
    setup = await mfa.setup_totp(db, services, user_id=user.id)
    return TotpSetupResponse(
        secret=setup.secret, otpauth_uri=setup.otpauth_uri, qr_svg=setup.qr_svg
    )


@router.post(
    "/mfa/totp/confirm", operation_id="confirmTotp", summary="Confirmar el enrolamiento TOTP"
)
async def confirm_totp(
    body: TotpConfirmRequest, user: AnyScopeUserDep, db: SessionDep, services: ServicesDep
) -> TotpConfirmResponse:
    result = await mfa.confirm_totp(
        db, services, user_id=user.id, session_id=user.session_id, code=body.code
    )
    return TotpConfirmResponse(
        recovery_codes=result.recovery_codes,
        access_token=result.access_token,
        expires_in=result.expires_in,
    )


@router.post(
    "/mfa/totp/disable",
    operation_id="disableTotp",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar TOTP (solo si el rol no lo exige)",
)
async def disable_totp(
    body: TotpDisableRequest, user: CurrentUserDep, db: SessionDep, services: ServicesDep
) -> None:
    await mfa.disable_totp(db, services, user_id=user.id, password=body.password, code=body.code)


@router.post(
    "/mfa/recovery-codes",
    operation_id="regenerateRecoveryCodes",
    summary="Generar nuevos códigos de recuperación",
)
async def regenerate_recovery_codes(
    body: RecoveryCodesRequest, user: CurrentUserDep, db: SessionDep, services: ServicesDep
) -> RecoveryCodesResponse:
    codes = await mfa.regenerate_recovery_codes(db, services, user_id=user.id, code=body.code)
    return RecoveryCodesResponse(recovery_codes=codes)


# --- own sessions --------------------------------------------------------------------------


@router.get("/sessions", operation_id="listMySessions", summary="Mis sesiones activas")
async def list_my_sessions(user: CurrentUserDep, db: SessionDep) -> list[SessionOut]:
    return [
        SessionOut.model_validate(session).model_copy(
            update={"current": session.id == user.session_id}
        )
        for session in await repo.active_sessions(db, user.id, utcnow())
    ]


@router.delete(
    "/sessions/{session_id}",
    operation_id="revokeMySession",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar una de mis sesiones",
)
async def revoke_my_session(session_id: uuid.UUID, user: CurrentUserDep, db: SessionDep) -> None:
    session = await repo.session_by_id(db, session_id, for_update=True)
    if session is None or session.user_id != user.id:
        raise NotFoundError("Sesión no encontrada.")
    await sessions.revoke_sessions(db, [session], reason="revoked_by_user")
    await db.commit()


@router.post(
    "/sessions/revoke-others",
    operation_id="revokeMyOtherSessions",
    summary="Cerrar todas mis demás sesiones",
)
async def revoke_other_sessions(user: CurrentUserDep, db: SessionDep) -> RevokedCount:
    count = await sessions.revoke_user_sessions(
        db, user.id, reason="revoked_by_user", except_session_id=user.session_id
    )
    await db.commit()
    return RevokedCount(revoked=count)
