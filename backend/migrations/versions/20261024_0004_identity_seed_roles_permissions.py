"""identity: seed phase B permissions and the five system roles (D-33)

Self-contained on purpose: migrations must not import application code. A test checks that
`app.modules.identity.permissions.PERMISSIONS` matches what migrations seed.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("identity.user.read", "identity", "read", "Consultar usuarios"),
    ("identity.user.create", "identity", "create", "Invitar usuarios"),
    ("identity.user.update", "identity", "update", "Editar datos de usuarios"),
    (
        "identity.user.disable",
        "identity",
        "disable",
        "Desactivar, reactivar y desbloquear usuarios",
    ),
    ("identity.user.assign_roles", "identity", "assign_roles", "Asignar roles a usuarios"),
    (
        "identity.user.reset_mfa",
        "identity",
        "reset_mfa",
        "Restablecer el segundo factor de un usuario",
    ),
    (
        "identity.user.revoke_sessions",
        "identity",
        "revoke_sessions",
        "Cerrar sesiones de otros usuarios",
    ),
    ("identity.role.read", "identity", "read", "Consultar roles"),
    ("identity.role.create", "identity", "create", "Crear roles"),
    ("identity.role.update", "identity", "update", "Editar roles y sus permisos"),
    ("identity.role.delete", "identity", "delete", "Eliminar roles"),
    ("identity.permission.read", "identity", "read", "Consultar el catálogo de permisos"),
    ("audit.log.read", "audit", "read", "Consultar la bitácora de auditoría"),
]

# code, name, description, requires_mfa, grants_all, permissions
ROLES = [
    (
        "superadmin",
        "Superadministrador",
        "Todos los permisos, sin alcance geográfico.",
        True,
        True,
        [],
    ),
    (
        "admin",
        "Administrador",
        "Gestión de usuarios dentro de su alcance y consulta de la bitácora.",
        True,
        False,
        [
            "identity.user.read",
            "identity.user.create",
            "identity.user.update",
            "identity.user.disable",
            "identity.user.assign_roles",
            "identity.user.reset_mfa",
            "identity.user.revoke_sessions",
            "identity.role.read",
            "identity.permission.read",
            "audit.log.read",
        ],
    ),
    ("coordinator", "Coordinador", "CRUD de candidaturas dentro de su alcance.", True, False, []),
    ("capturist", "Capturista", "Captura y edición sin aprobación.", False, False, []),
    ("viewer", "Consulta", "Solo lectura.", False, False, []),
]

permissions_table = sa.table(
    "permissions",
    sa.column("code", sa.String),
    sa.column("module", sa.String),
    sa.column("action", sa.String),
    sa.column("description", sa.String),
    schema="identity",
)
roles_table = sa.table(
    "roles",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("requires_mfa", sa.Boolean),
    sa.column("is_system", sa.Boolean),
    sa.column("grants_all", sa.Boolean),
    schema="identity",
)


def upgrade() -> None:
    op.bulk_insert(
        permissions_table,
        [{"code": c, "module": m, "action": a, "description": d} for c, m, a, d in PERMISSIONS],
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "code": code,
                "name": name,
                "description": description,
                "requires_mfa": requires_mfa,
                "is_system": True,
                "grants_all": grants_all,
            }
            for code, name, description, requires_mfa, grants_all, _ in ROLES
        ],
    )
    bind = op.get_bind()
    for code, *_, permission_codes in ROLES:
        for permission_code in permission_codes:
            bind.execute(
                sa.text(
                    "INSERT INTO identity.role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM identity.roles r, identity.permissions p "
                    "WHERE r.code = :role AND p.code = :permission"
                ),
                {"role": code, "permission": permission_code},
            )


def downgrade() -> None:
    codes = [code for code, *_ in ROLES]
    op.get_bind().execute(
        sa.text("DELETE FROM identity.roles WHERE code = ANY(:codes) AND is_system"),
        {"codes": codes},
    )
    op.get_bind().execute(
        sa.text("DELETE FROM identity.permissions WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in PERMISSIONS]},
    )
