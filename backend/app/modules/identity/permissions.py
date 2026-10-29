"""Permission codes of the core modules (identity, audit, geography, people, candidacies).

A new module declares its own `StrEnum` and points to it from its `module.py`; the catalog is
`app.core.modules.permission_codes()`. Every code is seeded by a migration, and
`tests/integration/identity/test_bootstrap_and_registry.py` fails if code and database drift
apart. The panel keeps a copy in `frontend/src/lib/auth/permissions.ts`, checked by
`tests/unit/test_module_registry.py`."""

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


SYSTEM_ROLES = ("superadmin", "admin", "coordinator", "capturist", "viewer")
