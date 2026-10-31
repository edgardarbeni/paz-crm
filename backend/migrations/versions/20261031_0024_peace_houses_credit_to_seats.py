"""peace_movement: Peace House credit to members or party structure seats (D-103, D-105)

- The credit goes to the member who opens the house (any level) or to a party structure seat;
  `credited_user_id` (zone coordinators, D-92) becomes `credited_position_id`, and a house can be
  opened by a seat (`opened_by_position_id`; `opened_by_member_id` becomes optional).
- Data: a house credited to a user moves to that person's seat when they hold exactly one;
  otherwise it goes to the tray (no credit). Both leave a credit change in the history.
- Zone coordinators are retired: their three tables are dropped.
- Permission `peace_movement.house.link`; the Constructor de Paz gets a national house goal of 1.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-31 00:54:22.064146+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSION = (
    "peace_movement.house.link",
    "house_link",
    "Abrir o enlazar Casas de Paz con crédito a un cargo propio de la estructura",
)
LINK_ROLES = ("admin", "coordinator", "territorial_leader", "territorial_coordinator")
# The user's single current seat (through the person's account), if exactly one.
_ONE_SEAT = """
SELECT pa.user_id, min(a.position_id::text)::uuid AS position_id
FROM party_structure.person_accounts pa
JOIN party_structure.appointments a ON a.person_id = pa.person_id
WHERE pa.deleted_at IS NULL AND a.ended_on IS NULL AND a.deleted_at IS NULL
GROUP BY pa.user_id HAVING count(*) = 1
"""


def _move_credit() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO peace_movement.peace_house_credit_changes (house_id, from_user_id, "
            "to_position_id, changed_at, reason) SELECT h.id, h.credited_user_id, s.position_id, "
            "now(), CASE WHEN s.position_id IS NULL THEN "
            "'D-103: el coordinador de zona no ocupa un solo cargo; la casa pasa a la bandeja.' "
            "ELSE 'D-103: el crédito pasa al cargo del coordinador de zona.' END "
            f"FROM peace_movement.peace_houses h LEFT JOIN ({_ONE_SEAT}) s "
            "ON s.user_id = h.credited_user_id WHERE h.credited_user_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE peace_movement.peace_houses h SET credited_position_id = s.position_id "
            f"FROM ({_ONE_SEAT}) s WHERE s.user_id = h.credited_user_id"
        )
    )


def _constraints(single_credit: str) -> None:
    op.drop_constraint("ck_peace_houses_single_credit", "peace_houses", schema="peace_movement")
    op.create_check_constraint(
        op.f("ck_peace_houses_single_credit"),
        "peace_houses",
        single_credit,
        schema="peace_movement",
    )


def _seed() -> None:
    bind = op.get_bind()
    code, action, description = PERMISSION
    bind.execute(
        sa.text(
            "INSERT INTO identity.permissions (code, module, action, description) "
            "VALUES (:code, 'peace_movement', :action, :description)"
        ),
        {"code": code, "action": action, "description": description},
    )
    for role in LINK_ROLES:
        bind.execute(
            sa.text(
                "INSERT INTO identity.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM identity.roles r, identity.permissions p "
                "WHERE r.code = :role AND p.code = :code"
            ),
            {"role": role, "code": code},
        )
    # D-103: the Constructor de Paz has a house goal (national seed of 1, adjustable per state).
    bind.execute(
        sa.text(
            "UPDATE peace_movement.level_goals g SET house_goal = 1, updated_at = now() "
            "FROM peace_movement.participation_levels l WHERE l.id = g.level_id "
            "AND l.code = 'peace_builder' AND g.state_id IS NULL AND g.valid_to IS NULL "
            "AND g.deleted_at IS NULL AND g.house_goal IS NULL"
        )
    )


def _down_data() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM identity.permissions WHERE code = :code"), {"code": PERMISSION[0]}
    )
    # Back to a user: the account of the seat's current holder, if any.
    bind.execute(
        sa.text(
            "UPDATE peace_movement.peace_houses h SET credited_user_id = pa.user_id "
            "FROM party_structure.appointments a JOIN party_structure.person_accounts pa "
            "ON pa.person_id = a.person_id WHERE a.position_id = h.credited_position_id "
            "AND a.ended_on IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE peace_movement.peace_houses SET opened_by_member_id = "
            "coalesce(opened_by_member_id, credited_member_id, host_member_id, contact_member_id) "
            "WHERE opened_by_member_id IS NULL"
        )
    )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_zone_coordinator_sections_section_id"),
        table_name="zone_coordinator_sections",
        schema="peace_movement",
    )
    op.drop_table("zone_coordinator_sections", schema="peace_movement")
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_federal_district_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_local_district_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_municipality_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_section_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_state_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_zone_coordinator_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_table("zone_coordinator_nodes", schema="peace_movement")
    op.drop_index(
        op.f("ix_zone_coordinators_state_id"),
        table_name="zone_coordinators",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinators_user_id"),
        table_name="zone_coordinators",
        schema="peace_movement",
    )
    op.drop_table("zone_coordinators", schema="peace_movement")
    op.add_column(
        "peace_house_credit_changes",
        sa.Column("from_position_id", sa.Uuid(), nullable=True),
        schema="peace_movement",
    )
    op.add_column(
        "peace_house_credit_changes",
        sa.Column("to_position_id", sa.Uuid(), nullable=True),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_peace_house_credit_changes_from_position_id"),
        "peace_house_credit_changes",
        ["from_position_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_peace_house_credit_changes_to_position_id"),
        "peace_house_credit_changes",
        ["to_position_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_foreign_key(
        op.f("fk_peace_house_credit_changes_from_position_id__positions"),
        "peace_house_credit_changes",
        "positions",
        ["from_position_id"],
        ["id"],
        source_schema="peace_movement",
        referent_schema="party_structure",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_peace_house_credit_changes_to_position_id__positions"),
        "peace_house_credit_changes",
        "positions",
        ["to_position_id"],
        ["id"],
        source_schema="peace_movement",
        referent_schema="party_structure",
        ondelete="RESTRICT",
    )
    op.add_column(
        "peace_houses",
        sa.Column("opened_by_position_id", sa.Uuid(), nullable=True),
        schema="peace_movement",
    )
    op.add_column(
        "peace_houses",
        sa.Column("credited_position_id", sa.Uuid(), nullable=True),
        schema="peace_movement",
    )
    op.alter_column(
        "peace_houses",
        "opened_by_member_id",
        existing_type=sa.UUID(),
        nullable=True,
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_peace_houses_credited_user_id"), table_name="peace_houses", schema="peace_movement"
    )
    op.create_index(
        op.f("ix_peace_houses_credited_position_id"),
        "peace_houses",
        ["credited_position_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_peace_houses_opened_by_position_id"),
        "peace_houses",
        ["opened_by_position_id"],
        unique=False,
        schema="peace_movement",
    )
    op.drop_constraint(
        op.f("fk_peace_houses_credited_user_id__users"),
        "peace_houses",
        schema="peace_movement",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_peace_houses_opened_by_position_id__positions"),
        "peace_houses",
        "positions",
        ["opened_by_position_id"],
        ["id"],
        source_schema="peace_movement",
        referent_schema="party_structure",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_peace_houses_credited_position_id__positions"),
        "peace_houses",
        "positions",
        ["credited_position_id"],
        ["id"],
        source_schema="peace_movement",
        referent_schema="party_structure",
        ondelete="RESTRICT",
    )
    _move_credit()
    _constraints("num_nonnulls(credited_member_id, credited_position_id) <= 1")
    op.create_check_constraint(
        op.f("ck_peace_houses_single_opener"),
        "peace_houses",
        "num_nonnulls(opened_by_member_id, opened_by_position_id) <= 1",
        schema="peace_movement",
    )
    op.drop_column("peace_houses", "credited_user_id", schema="peace_movement")
    _seed()
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "peace_houses",
        sa.Column("credited_user_id", sa.UUID(), autoincrement=False, nullable=True),
        schema="peace_movement",
    )
    _down_data()
    op.drop_constraint("ck_peace_houses_single_opener", "peace_houses", schema="peace_movement")
    _constraints("NOT (credited_member_id IS NOT NULL AND credited_user_id IS NOT NULL)")
    op.drop_constraint(
        op.f("fk_peace_houses_credited_position_id__positions"),
        "peace_houses",
        schema="peace_movement",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_peace_houses_opened_by_position_id__positions"),
        "peace_houses",
        schema="peace_movement",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_peace_houses_credited_user_id__users"),
        "peace_houses",
        "users",
        ["credited_user_id"],
        ["id"],
        source_schema="peace_movement",
        referent_schema="identity",
        ondelete="RESTRICT",
    )
    op.drop_index(
        op.f("ix_peace_houses_opened_by_position_id"),
        table_name="peace_houses",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_peace_houses_credited_position_id"),
        table_name="peace_houses",
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_peace_houses_credited_user_id"),
        "peace_houses",
        ["credited_user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.alter_column(
        "peace_houses",
        "opened_by_member_id",
        existing_type=sa.UUID(),
        nullable=False,
        schema="peace_movement",
    )
    op.drop_column("peace_houses", "credited_position_id", schema="peace_movement")
    op.drop_column("peace_houses", "opened_by_position_id", schema="peace_movement")
    op.drop_constraint(
        op.f("fk_peace_house_credit_changes_to_position_id__positions"),
        "peace_house_credit_changes",
        schema="peace_movement",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_peace_house_credit_changes_from_position_id__positions"),
        "peace_house_credit_changes",
        schema="peace_movement",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_peace_house_credit_changes_to_position_id"),
        table_name="peace_house_credit_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_peace_house_credit_changes_from_position_id"),
        table_name="peace_house_credit_changes",
        schema="peace_movement",
    )
    op.drop_column("peace_house_credit_changes", "to_position_id", schema="peace_movement")
    op.drop_column("peace_house_credit_changes", "from_position_id", schema="peace_movement")
    op.create_table(
        "zone_coordinators",
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
        sa.Column("user_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("state_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("valid_from", sa.DATE(), autoincrement=False, nullable=False),
        sa.Column("valid_to", sa.DATE(), autoincrement=False, nullable=True),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_zone_coordinators_validity")
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_zone_coordinators_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity.users.id"],
            name=op.f("fk_zone_coordinators_user_id__users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zone_coordinators")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinators_user_id"),
        "zone_coordinators",
        ["user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinators_state_id"),
        "zone_coordinators",
        ["state_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_table(
        "zone_coordinator_nodes",
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
        sa.Column("zone_coordinator_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("level", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("state_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("federal_district_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("local_district_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("municipality_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("section_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.CheckConstraint(
            "level = 'state'::text AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND state_id IS NOT NULL OR level = 'federal_district'::text AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND federal_district_id IS NOT NULL OR level = 'local_district'::text AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND local_district_id IS NOT NULL OR level = 'municipality'::text AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND municipality_id IS NOT NULL OR level = 'section'::text AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND section_id IS NOT NULL",
            name=op.f("ck_zone_coordinator_nodes_level_matches_node"),
        ),
        sa.CheckConstraint(
            "level = ANY (ARRAY['state'::text, 'federal_district'::text, 'local_district'::text, 'municipality'::text, 'section'::text])",
            name=op.f("ck_zone_coordinator_nodes_level"),
        ),
        sa.ForeignKeyConstraint(
            ["federal_district_id"],
            ["geography.federal_districts.id"],
            name=op.f("fk_zone_coordinator_nodes_federal_district_id__federal__148d"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["local_district_id"],
            ["geography.local_districts.id"],
            name=op.f("fk_zone_coordinator_nodes_local_district_id__local_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["geography.municipalities.id"],
            name=op.f("fk_zone_coordinator_nodes_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_zone_coordinator_nodes_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_zone_coordinator_nodes_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["zone_coordinator_id"],
            ["peace_movement.zone_coordinators.id"],
            name=op.f("fk_zone_coordinator_nodes_zone_coordinator_id__zone_coo_2e35"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zone_coordinator_nodes")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_zone_coordinator_id"),
        "zone_coordinator_nodes",
        ["zone_coordinator_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_state_id"),
        "zone_coordinator_nodes",
        ["state_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_section_id"),
        "zone_coordinator_nodes",
        ["section_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_municipality_id"),
        "zone_coordinator_nodes",
        ["municipality_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_local_district_id"),
        "zone_coordinator_nodes",
        ["local_district_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_federal_district_id"),
        "zone_coordinator_nodes",
        ["federal_district_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_table(
        "zone_coordinator_sections",
        sa.Column("zone_coordinator_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("section_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_zone_coordinator_sections_section_id__sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["zone_coordinator_id"],
            ["peace_movement.zone_coordinators.id"],
            name=op.f("fk_zone_coordinator_sections_zone_coordinator_id__zone__4d12"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "zone_coordinator_id", "section_id", name=op.f("pk_zone_coordinator_sections")
        ),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_sections_section_id"),
        "zone_coordinator_sections",
        ["section_id"],
        unique=False,
        schema="peace_movement",
    )
    # ### end Alembic commands ###
