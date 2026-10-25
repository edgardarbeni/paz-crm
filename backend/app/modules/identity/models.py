"""Identity tables (schema `identity`). See docs/MODELO_DATOS.md §2 and D-48."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    LargeBinary,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlmodel import Field, SQLModel

from app.core.db.base import BusinessTable, TimestampMixin

SCHEMA = "identity"
TZ = DateTime(timezone=True)


def _fk(table: str, *, ondelete: str = "CASCADE") -> Any:
    return Field(foreign_key=f"{SCHEMA}.{table}.id", ondelete=ondelete, index=True)  # type: ignore[call-overload]


def _check_in(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value.value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class UserStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    DISABLED = "disabled"


class User(BusinessTable, table=True):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email", "email", unique=True, postgresql_where=text("deleted_at IS NULL")),
        _check_in("status", UserStatus, "status"),
        {"schema": SCHEMA},
    )
    __audit_masked__: ClassVar[frozenset[str]] = frozenset({"password_hash"})

    email: str = Field(sa_type=CITEXT)
    full_name: str = Field(max_length=200)
    password_hash: str | None = None
    status: UserStatus = Field(default=UserStatus.INVITED, sa_type=Text)
    failed_login_count: int = Field(
        default=0, sa_type=SmallInteger, sa_column_kwargs={"server_default": text("0")}
    )
    locked_until: datetime | None = Field(default=None, sa_type=TZ)
    last_login_at: datetime | None = Field(default=None, sa_type=TZ)
    password_changed_at: datetime | None = Field(default=None, sa_type=TZ)


class Role(BusinessTable, table=True):
    __tablename__ = "roles"
    __table_args__ = (
        Index("uq_roles_code", "code", unique=True, postgresql_where=text("deleted_at IS NULL")),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,49}$'", name="code_format"),
        {"schema": SCHEMA},
    )

    code: str = Field(max_length=50)
    name: str = Field(max_length=100)
    description: str | None = None
    requires_mfa: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    is_system: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    # Implicitly holds every permission and is not limited by geographic scope (superadmin).
    grants_all: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})


class Permission(BusinessTable, table=True):
    __tablename__ = "permissions"
    __table_args__ = (
        Index(
            "uq_permissions_code", "code", unique=True, postgresql_where=text("deleted_at IS NULL")
        ),
        {"schema": SCHEMA},
    )

    code: str = Field(max_length=100)
    module: str = Field(max_length=50)
    action: str = Field(max_length=50)
    description: str


class RolePermission(TimestampMixin, table=True):
    __tablename__ = "role_permissions"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    role_id: uuid.UUID = Field(
        foreign_key=f"{SCHEMA}.roles.id", ondelete="CASCADE", primary_key=True
    )
    permission_id: uuid.UUID = Field(
        foreign_key=f"{SCHEMA}.permissions.id", ondelete="CASCADE", primary_key=True, index=True
    )


class UserRole(TimestampMixin, table=True):
    __tablename__ = "user_roles"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    user_id: uuid.UUID = Field(
        foreign_key=f"{SCHEMA}.users.id", ondelete="CASCADE", primary_key=True
    )
    role_id: uuid.UUID = Field(
        foreign_key=f"{SCHEMA}.roles.id", ondelete="CASCADE", primary_key=True, index=True
    )
    assigned_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key=f"{SCHEMA}.users.id", ondelete="SET NULL"
    )


class UserInvitation(BusinessTable, table=True):
    __tablename__ = "user_invitations"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    user_id: uuid.UUID = _fk("users")
    token_hash: bytes = Field(sa_type=LargeBinary, unique=True)
    invited_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key=f"{SCHEMA}.users.id", ondelete="SET NULL"
    )
    expires_at: datetime = Field(sa_type=TZ)
    accepted_at: datetime | None = Field(default=None, sa_type=TZ)
    revoked_at: datetime | None = Field(default=None, sa_type=TZ)


class PasswordResetToken(BusinessTable, table=True):
    __tablename__ = "password_reset_tokens"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    user_id: uuid.UUID = _fk("users")
    token_hash: bytes = Field(sa_type=LargeBinary, unique=True)
    requested_ip: str | None = Field(default=None, sa_type=INET)
    expires_at: datetime = Field(sa_type=TZ)
    used_at: datetime | None = Field(default=None, sa_type=TZ)


class TotpCredential(BusinessTable, table=True):
    __tablename__ = "totp_credentials"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    user_id: uuid.UUID = Field(foreign_key=f"{SCHEMA}.users.id", ondelete="CASCADE", unique=True)
    secret_ciphertext: bytes = Field(sa_type=LargeBinary)
    key_version: int = Field(sa_type=SmallInteger)
    confirmed_at: datetime | None = Field(default=None, sa_type=TZ)
    last_used_step: int | None = Field(default=None, sa_type=BigInteger)


class RecoveryCode(BusinessTable, table=True):
    __tablename__ = "recovery_codes"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}
    # Secrets regenerated in batches; "recovery_codes_regenerated" is audited explicitly.
    __audit__: ClassVar[bool] = False

    user_id: uuid.UUID = _fk("users")
    code_hash: bytes = Field(sa_type=LargeBinary)
    used_at: datetime | None = Field(default=None, sa_type=TZ)


class UserSession(BusinessTable, table=True):
    __tablename__ = "user_sessions"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}
    __audit_ignore_fields__: ClassVar[frozenset[str]] = frozenset({"last_seen_at", "ip_address"})

    user_id: uuid.UUID = _fk("users")
    device_label: str | None = Field(default=None, max_length=200)
    user_agent: str | None = None
    ip_address: str | None = Field(default=None, sa_type=INET)
    # How the session was authenticated, RFC 8176 values: ["pwd"] or ["pwd", "otp"].
    auth_methods: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    last_seen_at: datetime | None = Field(default=None, sa_type=TZ)
    expires_at: datetime = Field(sa_type=TZ)
    revoked_at: datetime | None = Field(default=None, sa_type=TZ)
    revoke_reason: str | None = Field(default=None, max_length=50)


class RefreshToken(BusinessTable, table=True):
    __tablename__ = "refresh_tokens"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}
    # Rotated on every refresh (high frequency); session lifecycle events are audited instead.
    __audit__: ClassVar[bool] = False

    session_id: uuid.UUID = _fk("user_sessions")
    token_hash: bytes = Field(sa_type=LargeBinary, unique=True)
    parent_token_id: uuid.UUID | None = Field(
        default=None, foreign_key=f"{SCHEMA}.refresh_tokens.id", ondelete="SET NULL"
    )
    expires_at: datetime = Field(sa_type=TZ)
    used_at: datetime | None = Field(default=None, sa_type=TZ)
    revoked_at: datetime | None = Field(default=None, sa_type=TZ)


ALL_TABLES: tuple[type[SQLModel], ...] = (
    User,
    Role,
    Permission,
    RolePermission,
    UserRole,
    UserInvitation,
    PasswordResetToken,
    TotpCredential,
    RecoveryCode,
    UserSession,
    RefreshToken,
)
