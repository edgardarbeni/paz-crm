"""party_structure: territorial coordinations (phase 4, D-110)

- Coordinations are bodies of three new body types (territorial level `coordination`, with
  `coordination_kind` federal, local or sectional) and have a `name`.
- Their territory: `coordination_federal_districts`, `coordination_local_districts` and
  `coordination_sections`, with `added_on` / `removed_on` and one current coordination per node.
- `coordination_position_types` (phase 1) moves into `position_types` of those body types, so
  their seats and appointments are the ordinary ones; the old table is dropped.
- Permissions `party_structure.coordination.read` / `.write`.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-30 23:25:13.664851+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEVELS = ("national", "state", "district", "municipal")
KINDS = ("federal", "local", "sectional")
# code, name, kind
COORDINATION_TYPES = [
    ("federal_coordination", "Coordinación federal", "federal"),
    ("local_coordination", "Coordinación local", "local"),
    ("sectional_coordination", "Coordinación seccional", "sectional"),
]
PERMISSIONS = [
    (
        "party_structure.coordination.read",
        "coordination_read",
        "Consultar coordinaciones territoriales",
    ),
    (
        "party_structure.coordination.write",
        "coordination_write",
        "Crear coordinaciones y cambiar su territorio",
    ),
]
READ, WRITE = (code for code, *_ in PERMISSIONS)
GRANTS = {
    "admin": [READ, WRITE],
    "coordinator": [READ, WRITE],
    "viewer": [READ],
    "territorial_leader": [READ, WRITE],
    "territorial_coordinator": [READ],
}


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _constraints_up() -> None:
    schema = "party_structure"
    op.drop_constraint("ck_body_types_territorial_level", "body_types", schema=schema)
    op.create_check_constraint(
        op.f("ck_body_types_territorial_level"),
        "body_types",
        f"territorial_level IN ({_in((*LEVELS, 'coordination'))})",
        schema=schema,
    )
    op.create_check_constraint(
        op.f("ck_body_types_coordination_kind"),
        "body_types",
        f"coordination_kind IN ({_in(KINDS)})",
        schema=schema,
    )
    op.create_check_constraint(
        op.f("ck_body_types_coordination_kind_set"),
        "body_types",
        "(territorial_level = 'coordination') = (coordination_kind IS NOT NULL)",
        schema=schema,
    )
    op.drop_constraint("ck_bodies_node_has_framework", "bodies", schema=schema)
    op.create_check_constraint(
        op.f("ck_bodies_node_has_framework"),
        "bodies",
        "num_nonnulls(municipality_id, federal_district_id, local_district_id) = 0 "
        "OR framework_id IS NOT NULL",
        schema=schema,
    )
    op.drop_index("uq_bodies_current", table_name="bodies", schema=schema)
    _bodies_index("dissolved_on IS NULL AND deleted_at IS NULL AND name IS NULL")


def _bodies_index(where: str) -> None:
    op.create_index(
        "uq_bodies_current",
        "bodies",
        [
            "body_type_id",
            sa.text("coalesce(state_code, 0)"),
            sa.text(
                "coalesce(municipality_id, federal_district_id, local_district_id, "
                "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
        ],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text(where),
    )


def _seed() -> None:
    bind = op.get_bind()
    start = bind.execute(
        sa.text("SELECT coalesce(max(sort_order), 0) FROM party_structure.body_types")
    ).scalar_one()
    for order, (code, name, kind) in enumerate(COORDINATION_TYPES, start=start + 1):
        bind.execute(
            sa.text(
                "INSERT INTO party_structure.body_types (code, name, territorial_level, "
                "requires_installation, coordination_kind, sort_order, description) "
                "VALUES (:code, :name, 'coordination', true, :kind, :order, "
                "'Coordinación territorial: estructura operativa por agrupación de territorio.')"
            ),
            {"code": code, "name": name, "kind": kind, "order": order},
        )
    # The coordination positions of phase 1 become positions of these body types.
    bind.execute(
        sa.text(
            "INSERT INTO party_structure.position_types (body_type_id, code, name, scope_rule, "
            "default_role_id, is_derived, sort_order) "
            "SELECT b.id, c.kind || '_' || c.code, c.name, 'body_territory', c.default_role_id, "
            "false, c.sort_order FROM party_structure.coordination_position_types c "
            "JOIN party_structure.body_types b ON b.coordination_kind = c.kind "
            "WHERE c.deleted_at IS NULL"
        )
    )
    for code, action, description in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO identity.permissions (code, module, action, description) "
                "VALUES (:code, 'party_structure', :action, :description)"
            ),
            {"code": code, "action": action, "description": description},
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


def _down_data() -> None:
    """Back to phase 3: coordination positions return to their own table; coordinations go."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO party_structure.coordination_position_types (kind, code, name, "
            "default_role_id, sort_order) SELECT b.coordination_kind, "
            "substr(p.code, length(b.coordination_kind) + 2), p.name, p.default_role_id, "
            "p.sort_order FROM party_structure.position_types p "
            "JOIN party_structure.body_types b ON b.id = p.body_type_id "
            "WHERE b.coordination_kind IS NOT NULL AND p.deleted_at IS NULL"
        )
    )
    for sql in (
        "DELETE FROM party_structure.derived_choices d USING party_structure.positions p, "
        "party_structure.bodies b, party_structure.body_types t WHERE p.id = d.position_id "
        "AND b.id = p.body_id AND t.id = b.body_type_id AND t.coordination_kind IS NOT NULL",
        "DELETE FROM party_structure.appointments a USING party_structure.positions p, "
        "party_structure.bodies b, party_structure.body_types t WHERE p.id = a.position_id "
        "AND b.id = p.body_id AND t.id = b.body_type_id AND t.coordination_kind IS NOT NULL",
        "DELETE FROM party_structure.positions p USING party_structure.position_types t, "
        "party_structure.body_types b WHERE t.id = p.position_type_id "
        "AND b.id = t.body_type_id AND b.coordination_kind IS NOT NULL",
        "DELETE FROM party_structure.bodies b USING party_structure.body_types t "
        "WHERE t.id = b.body_type_id AND t.coordination_kind IS NOT NULL",
        "DELETE FROM party_structure.position_derivations d USING party_structure.position_types "
        "t, party_structure.body_types b WHERE t.id = d.position_type_id "
        "AND b.id = t.body_type_id AND b.coordination_kind IS NOT NULL",
        "DELETE FROM party_structure.position_types t USING party_structure.body_types b "
        "WHERE b.id = t.body_type_id AND b.coordination_kind IS NOT NULL",
        "DELETE FROM party_structure.body_types WHERE coordination_kind IS NOT NULL",
    ):
        bind.execute(sa.text(sql))
    bind.execute(
        sa.text("DELETE FROM identity.permissions WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in PERMISSIONS]},
    )
    schema = "party_structure"
    op.drop_index("uq_bodies_current", table_name="bodies", schema=schema)
    _bodies_index("dissolved_on IS NULL AND deleted_at IS NULL")
    op.drop_constraint("ck_bodies_node_has_framework", "bodies", schema=schema)
    op.create_check_constraint(
        op.f("ck_bodies_node_has_framework"),
        "bodies",
        "(municipality_id IS NULL AND federal_district_id IS NULL "
        "AND local_district_id IS NULL) = (framework_id IS NULL)",
        schema=schema,
    )
    op.drop_constraint("ck_body_types_coordination_kind_set", "body_types", schema=schema)
    op.drop_constraint("ck_body_types_coordination_kind", "body_types", schema=schema)
    op.drop_constraint("ck_body_types_territorial_level", "body_types", schema=schema)
    op.create_check_constraint(
        op.f("ck_body_types_territorial_level"),
        "body_types",
        f"territorial_level IN ({_in(LEVELS)})",
        schema=schema,
    )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "coordination_federal_districts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coordination_id", sa.Uuid(), nullable=False),
        sa.Column("federal_district_id", sa.Uuid(), nullable=False),
        sa.Column("added_on", sa.Date(), nullable=False),
        sa.Column("removed_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["coordination_id"],
            ["party_structure.bodies.id"],
            name=op.f("fk_coordination_federal_districts_coordination_id__bodies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["federal_district_id"],
            ["geography.federal_districts.id"],
            name=op.f("fk_coordination_federal_districts_federal_district_id__federal_districts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coordination_federal_districts")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_federal_districts_coordination_id"),
        "coordination_federal_districts",
        ["coordination_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_federal_districts_federal_district_id"),
        "coordination_federal_districts",
        ["federal_district_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_coordination_federal_districts_current",
        "coordination_federal_districts",
        ["federal_district_id"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("removed_on IS NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "coordination_local_districts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coordination_id", sa.Uuid(), nullable=False),
        sa.Column("local_district_id", sa.Uuid(), nullable=False),
        sa.Column("added_on", sa.Date(), nullable=False),
        sa.Column("removed_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["coordination_id"],
            ["party_structure.bodies.id"],
            name=op.f("fk_coordination_local_districts_coordination_id__bodies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["local_district_id"],
            ["geography.local_districts.id"],
            name=op.f("fk_coordination_local_districts_local_district_id__local_districts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coordination_local_districts")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_local_districts_coordination_id"),
        "coordination_local_districts",
        ["coordination_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_local_districts_local_district_id"),
        "coordination_local_districts",
        ["local_district_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_coordination_local_districts_current",
        "coordination_local_districts",
        ["local_district_id"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("removed_on IS NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "coordination_sections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coordination_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("added_on", sa.Date(), nullable=False),
        sa.Column("removed_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["coordination_id"],
            ["party_structure.bodies.id"],
            name=op.f("fk_coordination_sections_coordination_id__bodies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_coordination_sections_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coordination_sections")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_sections_coordination_id"),
        "coordination_sections",
        ["coordination_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_sections_section_id"),
        "coordination_sections",
        ["section_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_coordination_sections_current",
        "coordination_sections",
        ["section_id"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("removed_on IS NULL AND deleted_at IS NULL"),
    )
    op.add_column(
        "bodies",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        schema="party_structure",
    )
    op.add_column(
        "body_types",
        sa.Column("coordination_kind", sa.Text(), nullable=True),
        schema="party_structure",
    )
    _constraints_up()
    _seed()
    op.drop_index(
        op.f("ix_coordination_position_types_default_role_id"),
        table_name="coordination_position_types",
        schema="party_structure",
    )
    op.drop_index(
        op.f("uq_coordination_position_types_kind_code"),
        table_name="coordination_position_types",
        schema="party_structure",
        postgresql_where="(deleted_at IS NULL)",
    )
    op.drop_table("coordination_position_types", schema="party_structure")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "coordination_position_types",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("uuidv7()"), autoincrement=False, nullable=False
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "deleted_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
        sa.Column("kind", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("code", sa.VARCHAR(length=80), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(length=200), autoincrement=False, nullable=False),
        sa.Column("default_role_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("sort_order", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.CheckConstraint(
            "kind = ANY (ARRAY['federal'::text, 'local'::text, 'sectional'::text])",
            name=op.f("ck_coordination_position_types_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["default_role_id"],
            ["identity.roles.id"],
            name=op.f("fk_coordination_position_types_default_role_id__roles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coordination_position_types")),
        schema="party_structure",
    )
    op.create_index(
        op.f("uq_coordination_position_types_kind_code"),
        "coordination_position_types",
        ["kind", "code"],
        unique=True,
        schema="party_structure",
        postgresql_where="(deleted_at IS NULL)",
    )
    op.create_index(
        op.f("ix_coordination_position_types_default_role_id"),
        "coordination_position_types",
        ["default_role_id"],
        unique=False,
        schema="party_structure",
    )
    op.drop_index(
        "uq_coordination_sections_current",
        table_name="coordination_sections",
        schema="party_structure",
        postgresql_where=sa.text("removed_on IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_coordination_sections_section_id"),
        table_name="coordination_sections",
        schema="party_structure",
    )
    op.drop_index(
        op.f("ix_coordination_sections_coordination_id"),
        table_name="coordination_sections",
        schema="party_structure",
    )
    op.drop_table("coordination_sections", schema="party_structure")
    op.drop_index(
        "uq_coordination_local_districts_current",
        table_name="coordination_local_districts",
        schema="party_structure",
        postgresql_where=sa.text("removed_on IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_coordination_local_districts_local_district_id"),
        table_name="coordination_local_districts",
        schema="party_structure",
    )
    op.drop_index(
        op.f("ix_coordination_local_districts_coordination_id"),
        table_name="coordination_local_districts",
        schema="party_structure",
    )
    op.drop_table("coordination_local_districts", schema="party_structure")
    op.drop_index(
        "uq_coordination_federal_districts_current",
        table_name="coordination_federal_districts",
        schema="party_structure",
        postgresql_where=sa.text("removed_on IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_coordination_federal_districts_federal_district_id"),
        table_name="coordination_federal_districts",
        schema="party_structure",
    )
    op.drop_index(
        op.f("ix_coordination_federal_districts_coordination_id"),
        table_name="coordination_federal_districts",
        schema="party_structure",
    )
    op.drop_table("coordination_federal_districts", schema="party_structure")
    # ### end Alembic commands ###
    _down_data()
    op.drop_column("body_types", "coordination_kind", schema="party_structure")
    op.drop_column("bodies", "name", schema="party_structure")
