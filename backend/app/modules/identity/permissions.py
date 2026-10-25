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
    USER_ASSIGN_SCOPES = "identity.user.assign_scopes"
    AUDIT_READ = "audit.log.read"
    GEOGRAPHY_READ = "geography.node.read"
    GEOGRAPHY_IMPORT_READ = "geography.import.read"
    PERSON_READ = "people.person.read"
    PERSON_WRITE = "people.person.write"
    PERSON_READ_SENSITIVE = "people.person.read_sensitive"
    PERSON_DELETE = "people.person.delete"
    CANDIDACIES_READ = "candidacies.read"
    CATALOG_MANAGE = "candidacies.catalog.manage"
    PROCESS_MANAGE = "candidacies.process.manage"
    NOMINATION_WRITE = "candidacies.nomination.write"
    NOMINATION_APPROVE = "candidacies.nomination.approve"
    RULE_OVERRIDE = "candidacies.rule.override"


PERMISSIONS: frozenset[str] = frozenset(Perm)
SYSTEM_ROLES = ("superadmin", "admin", "coordinator", "capturist", "viewer")
