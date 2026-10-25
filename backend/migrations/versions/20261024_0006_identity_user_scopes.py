"""identity: geographic scopes (user_scopes, derived user_scope_sections) and phase C permissions

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25 01:04:25.737571+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = [
    (
        "identity.user.assign_scopes",
        "identity",
        "assign_scopes",
        "Asignar alcance geográfico a usuarios",
    ),
    ("geography.node.read", "geography", "read", "Consultar la geografía electoral"),
    ("geography.import.read", "geography", "read", "Consultar las importaciones geográficas"),
]
GRANTS = {
    "admin": ["identity.user.assign_scopes", "geography.node.read", "geography.import.read"],
    "coordinator": ["geography.node.read"],
    "capturist": ["geography.node.read"],
    "viewer": ["geography.node.read"],
}


def _seed() -> None:
    bind = op.get_bind()
    for code, module, action, description in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO identity.permissions (code, module, action, description) "
                "VALUES (:code, :module, :action, :description)"
            ),
            {"code": code, "module": module, "action": action, "description": description},
        )
    for role, codes in GRANTS.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO identity.role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM identity.roles r, identity.permissions p "
                    "WHERE r.code = :role AND p.code = :code"
                ),
                {"role": role, "code": code},
            )


def _unseed() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM identity.permissions WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in PERMISSIONS]},
    )


def upgrade() -> None:
    op.create_table(
        "user_scope_sections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_user_scope_sections_section_id__sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity.users.id"],
            name=op.f("fk_user_scope_sections_user_id__users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "section_id", name=op.f("pk_user_scope_sections")),
        schema="identity",
    )
    op.create_index(
        op.f("ix_user_scope_sections_section_id"),
        "user_scope_sections",
        ["section_id"],
        unique=False,
        schema="identity",
    )
    op.create_table(
        "user_scopes",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope_level", sa.Text(), nullable=False),
        sa.Column("electoral_region_id", sa.Uuid(), nullable=True),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("federal_district_id", sa.Uuid(), nullable=True),
        sa.Column("local_district_id", sa.Uuid(), nullable=True),
        sa.Column("municipality_id", sa.Uuid(), nullable=True),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(scope_level = 'electoral_region' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND electoral_region_id IS NOT NULL) OR (scope_level = 'state' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND state_id IS NOT NULL) OR (scope_level = 'federal_district' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND federal_district_id IS NOT NULL) OR (scope_level = 'local_district' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND local_district_id IS NOT NULL) OR (scope_level = 'municipality' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND municipality_id IS NOT NULL) OR (scope_level = 'section' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND section_id IS NOT NULL) OR (scope_level = 'national' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, section_id) = 0)",
            name=op.f("ck_user_scopes_level_matches_node"),
        ),
        sa.CheckConstraint(
            "scope_level IN ('national', 'electoral_region', 'state', 'federal_district', 'local_district', 'municipality', 'section')",
            name=op.f("ck_user_scopes_scope_level"),
        ),
        sa.ForeignKeyConstraint(
            ["electoral_region_id"],
            ["geography.electoral_regions.id"],
            name=op.f("fk_user_scopes_electoral_region_id__electoral_regions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["federal_district_id"],
            ["geography.federal_districts.id"],
            name=op.f("fk_user_scopes_federal_district_id__federal_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["local_district_id"],
            ["geography.local_districts.id"],
            name=op.f("fk_user_scopes_local_district_id__local_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["geography.municipalities.id"],
            name=op.f("fk_user_scopes_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_user_scopes_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_user_scopes_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity.users.id"],
            name=op.f("fk_user_scopes_user_id__users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_scopes")),
        schema="identity",
    )
    op.create_index(
        op.f("ix_user_scopes_user_id"), "user_scopes", ["user_id"], unique=False, schema="identity"
    )

    _seed()


def downgrade() -> None:
    _unseed()
    op.drop_index(op.f("ix_user_scopes_user_id"), table_name="user_scopes", schema="identity")
    op.drop_table("user_scopes", schema="identity")
    op.drop_index(
        op.f("ix_user_scope_sections_section_id"),
        table_name="user_scope_sections",
        schema="identity",
    )
    op.drop_table("user_scope_sections", schema="identity")
