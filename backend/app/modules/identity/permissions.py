"""Permission registry. Each module declares its permission codes here (or in its own
`permissions.py`) and seeds them with a migration; `tests/.../test_permissions_registry.py`
fails if code and database drift apart."""

from enum import StrEnum


class Perm(StrEnum):
    USER_READ = "identity.user.read"
    USER_CREATE = "identity.user.create"
    USER_UPDATE = "identity.user.update"
    USER_DISABLE = "identity.user.disable"
    USER_ASSIGN_ROLES = "identity.user.assign_roles"
    USER_RESET_MFA = "identity.user.reset_mfa"
    USER_REVOKE_SESSIONS = "identity.user.revoke_sessions"
    ROLE_READ = "identity.role.read"
    ROLE_CREATE = "identity.role.create"
    ROLE_UPDATE = "identity.role.update"
    ROLE_DELETE = "identity.role.delete"
    PERMISSION_READ = "identity.permission.read"
    AUDIT_READ = "audit.log.read"


PERMISSIONS: frozenset[str] = frozenset(Perm)
SYSTEM_ROLES = ("superadmin", "admin", "coordinator", "capturist", "viewer")
