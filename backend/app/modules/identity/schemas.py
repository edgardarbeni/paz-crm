"""Request/response schemas (DTOs). Table models never leave the service layer."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints

from app.modules.identity.models import (
    SCOPE_COLUMNS,
    GrantOrigin,
    ScopeLevel,
    UserGrant,
    UserGrantScope,
    UserStatus,
)
from app.modules.identity.security.tokens import TokenScope

Password = Annotated[str, Field(min_length=1, max_length=256)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
TotpCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=8)]
RoleCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,49}$")]
# PostgreSQL INET values arrive as ipaddress objects.
IpText = Annotated[str | None, BeforeValidator(lambda v: None if v is None else str(v))]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# --- authentication ----------------------------------------------------------------------


class LoginRequest(Schema):
    email: EmailStr
    password: Password
    device_label: Annotated[str | None, Field(max_length=200)] = None


class MfaVerifyRequest(Schema):
    mfa_token: str = Field(max_length=2048)
    code: TotpCode | None = None
    recovery_code: Annotated[str | None, Field(max_length=32)] = None
    device_label: Annotated[str | None, Field(max_length=200)] = None


class AuthStatus(StrEnum):
    AUTHENTICATED = "authenticated"
    MFA_REQUIRED = "mfa_required"


class AuthenticatedResponse(Schema):
    status: Literal[AuthStatus.AUTHENTICATED] = AuthStatus.AUTHENTICATED
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 - token scheme, not a secret
    expires_in: int = Field(description="Segundos de vida del access token.")
    scope: TokenScope = Field(
        description="`mfa_enrollment`: el rol exige 2FA y solo se permite enrolar TOTP."
    )


class MfaRequiredResponse(Schema):
    status: Literal[AuthStatus.MFA_REQUIRED] = AuthStatus.MFA_REQUIRED
    mfa_token: str = Field(description="Enviar a /auth/mfa/verify junto con el código TOTP.")
    expires_in: int


LoginResponse = Annotated[
    AuthenticatedResponse | MfaRequiredResponse, Field(discriminator="status")
]


class RoleSummary(Schema):
    id: uuid.UUID
    code: str
    name: str
    grants_all: bool = Field(default=False, description="Superadministrador: todo, sin alcance.")


class ScopeIn(Schema):
    level: ScopeLevel
    node_id: uuid.UUID | None = Field(default=None, description="Vacío para `national`.")


class ScopeOut(Schema):
    id: uuid.UUID
    level: ScopeLevel
    node_id: uuid.UUID | None

    @classmethod
    def from_model(cls, scope: UserGrantScope) -> "ScopeOut":
        level = ScopeLevel(scope.scope_level)
        node = getattr(scope, SCOPE_COLUMNS[level]) if level in SCOPE_COLUMNS else None
        assert scope.id is not None  # noqa: S101
        return cls(id=scope.id, level=level, node_id=node)


class GrantOut(Schema):
    """A (role, scope) pair (D-101): the role's permissions apply only inside its scopes."""

    id: uuid.UUID
    role: RoleSummary
    origin: GrantOrigin
    source_id: uuid.UUID | None = Field(description="Nombramiento que la originó, si aplica.")
    scopes: list[ScopeOut]
    created_at: datetime

    @classmethod
    def from_parts(cls, grant: UserGrant, role: Any, scopes: list[UserGrantScope]) -> "GrantOut":
        assert grant.id is not None  # noqa: S101
        assert grant.created_at is not None  # noqa: S101
        return cls(
            id=grant.id,
            role=RoleSummary.model_validate(role),
            origin=GrantOrigin(grant.origin),
            source_id=grant.source_id,
            scopes=[ScopeOut.from_model(scope) for scope in scopes],
            created_at=grant.created_at,
        )


class GrantIn(Schema):
    id: uuid.UUID | None = Field(
        default=None,
        description="Concesión manual existente que se conserva; vacío para una nueva.",
    )
    role_id: uuid.UUID
    scopes: list[ScopeIn] = Field(
        default_factory=list, max_length=50, description="Sin alcance no ve nada."
    )


class GrantsRequest(Schema):
    grants: list[GrantIn] = Field(max_length=20)


class MfaStatus(Schema):
    enabled: bool
    required: bool


class MeResponse(Schema):
    id: uuid.UUID
    email: str
    full_name: str
    status: UserStatus
    roles: list[RoleSummary]
    permissions: list[str]
    grants_all: bool
    mfa: MfaStatus
    session_id: uuid.UUID
    scope: TokenScope
    geo_unrestricted: bool = Field(
        description="Alguna concesión ve todo el país (superadmin o alcance nacional)."
    )
    grants: list[GrantOut]


class PasswordChangeRequest(Schema):
    current_password: Password
    new_password: Password


class PasswordForgotRequest(Schema):
    email: EmailStr


class PasswordResetRequest(Schema):
    token: str = Field(max_length=256)
    new_password: Password


class InvitationTokenRequest(Schema):
    token: str = Field(max_length=256)


class InvitationInfo(Schema):
    email: str
    full_name: str
    expires_at: datetime


class InvitationAcceptRequest(Schema):
    token: str = Field(max_length=256)
    password: Password
    full_name: FullName | None = None


# --- MFA ---------------------------------------------------------------------------------


class TotpSetupResponse(Schema):
    secret: str = Field(description="Clave para captura manual en la app autenticadora.")
    otpauth_uri: str
    qr_svg: str = Field(description="Código QR como data URI SVG.")


class TotpConfirmRequest(Schema):
    code: TotpCode


class TotpConfirmResponse(Schema):
    recovery_codes: list[str] = Field(description="Se muestran una sola vez.")
    access_token: str = Field(description="Nuevo access token con alcance completo.")
    expires_in: int


class TotpDisableRequest(Schema):
    password: Password
    code: TotpCode


class RecoveryCodesRequest(Schema):
    code: TotpCode


class RecoveryCodesResponse(Schema):
    recovery_codes: list[str]


# --- sessions ----------------------------------------------------------------------------


class SessionOut(Schema):
    id: uuid.UUID
    device_label: str | None
    user_agent: str | None
    ip_address: IpText
    auth_methods: list[str]
    created_at: datetime
    last_seen_at: datetime | None
    expires_at: datetime
    current: bool = False


class RevokedCount(Schema):
    revoked: int


# --- users (administration) --------------------------------------------------------------


class UserInviteRequest(Schema):
    email: EmailStr
    full_name: FullName
    role_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class UserUpdateRequest(Schema):
    full_name: FullName


class UserOut(Schema):
    id: uuid.UUID
    email: str
    full_name: str
    status: UserStatus
    roles: list[RoleSummary]
    mfa_enabled: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserInvitedResponse(UserOut):
    invitation_expires_at: datetime


# --- roles & permissions -----------------------------------------------------------------


class PermissionOut(Schema):
    id: uuid.UUID
    code: str
    module: str
    action: str
    description: str


class RoleOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    requires_mfa: bool
    is_system: bool
    grants_all: bool
    permissions: list[str]
    user_count: int


class RoleCreateRequest(Schema):
    code: RoleCode
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    description: Annotated[str | None, Field(max_length=500)] = None
    requires_mfa: bool = False
    permissions: list[str] = Field(default_factory=list, max_length=200)


class RoleUpdateRequest(Schema):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
        | None
    ) = None
    description: Annotated[str | None, Field(max_length=500)] = None
    requires_mfa: bool | None = None


class RolePermissionsRequest(Schema):
    permissions: list[str] = Field(max_length=200)


# --- audit log ---------------------------------------------------------------------------


class AuditEntryOut(Schema):
    id: uuid.UUID
    chain_seq: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_ip: IpText
    user_agent: str | None
    request_id: str | None
    action: str
    entity_table: str | None
    entity_id: str | None
    before: dict[str, object] | None
    after: dict[str, object] | None


class AccessEntryOut(Schema):
    """A sensitive read (D-89): who read what, never the content."""

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_ip: IpText
    user_agent: str | None
    request_id: str | None
    action: str
    entity_table: str
    entity_id: str | None
    details: dict[str, object] | None
