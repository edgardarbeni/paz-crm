"""peace_movement: schema, ltree and the tables of the pyramid, goals and zones (D-91, D-92)

- Extension `ltree` (contrib, available in the project image, DigitalOcean and RDS).
- Schema `peace_movement` with the default privileges of every module schema.
- Sequence `member_tree_ids`: internal bigint labels of the `ltree` paths.
- Tables: catalogs and goals, settings, zone coordinators (with derived sections), members and
  their histories, branch scopes and the `network_changes` outbox.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-29
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType

from migrations.helpers import app_role, if_role_exists

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class Ltree(UserDefinedType[str]):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "ltree"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree WITH SCHEMA public")
    op.execute("CREATE SCHEMA IF NOT EXISTS peace_movement")
    op.execute("REVOKE ALL ON SCHEMA peace_movement FROM PUBLIC")
    role = app_role()
    op.execute(
        if_role_exists(
            role,
            f"""
            GRANT USAGE ON SCHEMA peace_movement TO {role};
            ALTER DEFAULT PRIVILEGES IN SCHEMA peace_movement
              GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role};
            ALTER DEFAULT PRIVILEGES IN SCHEMA peace_movement
              GRANT USAGE, SELECT ON SEQUENCES TO {role};
            """,
        )
    )
    op.execute("CREATE SEQUENCE peace_movement.member_tree_ids AS bigint")
    op.create_table(
        "network_changes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("paths", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_network_changes")),
        schema="peace_movement",
    )
    op.create_index(
        "ix_network_changes_pending",
        "network_changes",
        ["id"],
        unique=False,
        schema="peace_movement",
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_table(
        "participation_levels",
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
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participation_levels")),
        sa.UniqueConstraint("code", name=op.f("uq_participation_levels_code")),
        sa.UniqueConstraint("rank", name=op.f("uq_participation_levels_rank")),
        schema="peace_movement",
    )
    op.create_table(
        "settings",
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
        sa.Column("traffic_light_yellow_pct", sa.SmallInteger(), nullable=False),
        sa.Column("traffic_light_green_pct", sa.SmallInteger(), nullable=False),
        sa.Column("depth_alert_threshold", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "0 < traffic_light_yellow_pct AND traffic_light_yellow_pct < traffic_light_green_pct",
            name=op.f("ck_settings_traffic_light"),
        ),
        sa.CheckConstraint(
            "depth_alert_threshold > 0", name=op.f("ck_settings_depth_alert_threshold")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        schema="peace_movement",
    )
    op.create_index(
        "uq_settings_singleton",
        "settings",
        [sa.literal_column("(true)")],
        unique=True,
        schema="peace_movement",
    )
    op.create_table(
        "house_goals",
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
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("member_goal", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.CheckConstraint("member_goal > 0", name=op.f("ck_house_goals_member_goal")),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_house_goals_validity")
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_house_goals_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_house_goals")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_house_goals_state_id"),
        "house_goals",
        ["state_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        "uq_house_goals_current",
        "house_goals",
        [sa.literal_column("coalesce(state_id, '00000000-0000-0000-0000-000000000000'::uuid)")],
        unique=True,
        schema="peace_movement",
        postgresql_where=sa.text("valid_to IS NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "level_goals",
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
        sa.Column("level_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("recruit_goal", sa.Integer(), nullable=False),
        sa.Column("house_goal", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "house_goal IS NULL OR house_goal >= 0", name=op.f("ck_level_goals_house_goal")
        ),
        sa.CheckConstraint("recruit_goal >= 0", name=op.f("ck_level_goals_recruit_goal")),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_level_goals_validity")
        ),
        sa.ForeignKeyConstraint(
            ["level_id"],
            ["peace_movement.participation_levels.id"],
            name=op.f("fk_level_goals_level_id__participation_levels"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_level_goals_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_level_goals")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_level_goals_level_id"),
        "level_goals",
        ["level_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_level_goals_state_id"),
        "level_goals",
        ["state_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        "uq_level_goals_current",
        "level_goals",
        [
            "level_id",
            sa.literal_column("coalesce(state_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
        ],
        unique=True,
        schema="peace_movement",
        postgresql_where=sa.text("valid_to IS NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "zone_coordinators",
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
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
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
        op.f("ix_zone_coordinators_state_id"),
        "zone_coordinators",
        ["state_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinators_user_id"),
        "zone_coordinators",
        ["user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_table(
        "members",
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
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("enrolled_on", sa.Date(), nullable=False),
        sa.Column("level_id", sa.Uuid(), nullable=False),
        sa.Column("recruited_by_member_id", sa.Uuid(), nullable=True),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("origin_detail", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("registered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("status_reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("validated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_on", sa.Date(), nullable=True),
        sa.Column("referral_code", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("tree_id", sa.BigInteger(), nullable=False),
        sa.Column("path", Ltree(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("consent_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(origin = 'recruiter') = (recruited_by_member_id IS NOT NULL)",
            name=op.f("ck_members_recruiter"),
        ),
        sa.CheckConstraint(
            "channel IN ('panel', 'referral_link', 'import', 'field_app')",
            name=op.f("ck_members_channel"),
        ),
        sa.CheckConstraint(
            "origin IN ('recruiter', 'structure', 'event', 'campaign')",
            name=op.f("ck_members_origin"),
        ),
        sa.CheckConstraint(
            "status IN ('pending_validation', 'active', 'rejected', 'left', 'withdrawn')",
            name=op.f("ck_members_status"),
        ),
        sa.CheckConstraint("depth >= 0", name=op.f("ck_members_depth")),
        sa.ForeignKeyConstraint(
            ["consent_id"],
            ["people.privacy_consents.id"],
            name=op.f("fk_members_consent_id__privacy_consents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["level_id"],
            ["peace_movement.participation_levels.id"],
            name=op.f("fk_members_level_id__participation_levels"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.persons.id"],
            name=op.f("fk_members_person_id__persons"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recruited_by_member_id"],
            ["peace_movement.members.id"],
            name=op.f("fk_members_recruited_by_member_id__members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["registered_by_user_id"],
            ["identity.users.id"],
            name=op.f("fk_members_registered_by_user_id__users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_members_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_members_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["validated_by_user_id"],
            ["identity.users.id"],
            name=op.f("fk_members_validated_by_user_id__users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_members")),
        sa.UniqueConstraint("referral_code", name=op.f("uq_members_referral_code")),
        sa.UniqueConstraint("tree_id", name=op.f("uq_members_tree_id")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_members_consent_id"),
        "members",
        ["consent_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_members_level_id"), "members", ["level_id"], unique=False, schema="peace_movement"
    )
    op.create_index(
        "ix_members_path",
        "members",
        ["path"],
        unique=False,
        schema="peace_movement",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_members_person_id"),
        "members",
        ["person_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_members_recruited_by_member_id"),
        "members",
        ["recruited_by_member_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_members_registered_by_user_id"),
        "members",
        ["registered_by_user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_members_section_id"),
        "members",
        ["section_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_members_state_id"), "members", ["state_id"], unique=False, schema="peace_movement"
    )
    op.create_index(
        op.f("ix_members_validated_by_user_id"),
        "members",
        ["validated_by_user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        "uq_members_current_person",
        "members",
        ["person_id"],
        unique=True,
        schema="peace_movement",
        postgresql_where=sa.text(
            "status IN ('pending_validation', 'active') AND deleted_at IS NULL"
        ),
    )
    op.create_table(
        "zone_coordinator_nodes",
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
        sa.Column("zone_coordinator_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("federal_district_id", sa.Uuid(), nullable=True),
        sa.Column("local_district_id", sa.Uuid(), nullable=True),
        sa.Column("municipality_id", sa.Uuid(), nullable=True),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(level = 'state' AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND state_id IS NOT NULL) OR (level = 'federal_district' AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND federal_district_id IS NOT NULL) OR (level = 'local_district' AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND local_district_id IS NOT NULL) OR (level = 'municipality' AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND municipality_id IS NOT NULL) OR (level = 'section' AND num_nonnulls(state_id, federal_district_id, local_district_id, municipality_id, section_id) = 1 AND section_id IS NOT NULL)",
            name=op.f("ck_zone_coordinator_nodes_level_matches_node"),
        ),
        sa.CheckConstraint(
            "level IN ('state', 'federal_district', 'local_district', 'municipality', 'section')",
            name=op.f("ck_zone_coordinator_nodes_level"),
        ),
        sa.ForeignKeyConstraint(
            ["federal_district_id"],
            ["geography.federal_districts.id"],
            name=op.f("fk_zone_coordinator_nodes_federal_district_id__federal_districts"),
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
            name=op.f("fk_zone_coordinator_nodes_zone_coordinator_id__zone_coordinators"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zone_coordinator_nodes")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_federal_district_id"),
        "zone_coordinator_nodes",
        ["federal_district_id"],
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
        op.f("ix_zone_coordinator_nodes_municipality_id"),
        "zone_coordinator_nodes",
        ["municipality_id"],
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
        op.f("ix_zone_coordinator_nodes_state_id"),
        "zone_coordinator_nodes",
        ["state_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_zone_coordinator_nodes_zone_coordinator_id"),
        "zone_coordinator_nodes",
        ["zone_coordinator_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_table(
        "zone_coordinator_sections",
        sa.Column("zone_coordinator_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_zone_coordinator_sections_section_id__sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["zone_coordinator_id"],
            ["peace_movement.zone_coordinators.id"],
            name=op.f("fk_zone_coordinator_sections_zone_coordinator_id__zone_coordinators"),
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
    op.create_table(
        "member_level_changes",
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
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("from_level_id", sa.Uuid(), nullable=False),
        sa.Column("to_level_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["identity.users.id"],
            name=op.f("fk_member_level_changes_changed_by_user_id__users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["from_level_id"],
            ["peace_movement.participation_levels.id"],
            name=op.f("fk_member_level_changes_from_level_id__participation_levels"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["peace_movement.members.id"],
            name=op.f("fk_member_level_changes_member_id__members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_level_id"],
            ["peace_movement.participation_levels.id"],
            name=op.f("fk_member_level_changes_to_level_id__participation_levels"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_level_changes")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_level_changes_changed_by_user_id"),
        "member_level_changes",
        ["changed_by_user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_level_changes_from_level_id"),
        "member_level_changes",
        ["from_level_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_level_changes_member_id"),
        "member_level_changes",
        ["member_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_level_changes_to_level_id"),
        "member_level_changes",
        ["to_level_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_table(
        "member_recruiter_changes",
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
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("from_member_id", sa.Uuid(), nullable=True),
        sa.Column("to_member_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("subtree_size", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["identity.users.id"],
            name=op.f("fk_member_recruiter_changes_changed_by_user_id__users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["from_member_id"],
            ["peace_movement.members.id"],
            name=op.f("fk_member_recruiter_changes_from_member_id__members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["peace_movement.members.id"],
            name=op.f("fk_member_recruiter_changes_member_id__members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_member_id"],
            ["peace_movement.members.id"],
            name=op.f("fk_member_recruiter_changes_to_member_id__members"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_recruiter_changes")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_recruiter_changes_changed_by_user_id"),
        "member_recruiter_changes",
        ["changed_by_user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_recruiter_changes_from_member_id"),
        "member_recruiter_changes",
        ["from_member_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_recruiter_changes_member_id"),
        "member_recruiter_changes",
        ["member_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_member_recruiter_changes_to_member_id"),
        "member_recruiter_changes",
        ["to_member_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_table(
        "user_branch_scopes",
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
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["peace_movement.members.id"],
            name=op.f("fk_user_branch_scopes_member_id__members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity.users.id"],
            name=op.f("fk_user_branch_scopes_user_id__users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_branch_scopes")),
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_user_branch_scopes_member_id"),
        "user_branch_scopes",
        ["member_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        op.f("ix_user_branch_scopes_user_id"),
        "user_branch_scopes",
        ["user_id"],
        unique=False,
        schema="peace_movement",
    )
    op.create_index(
        "uq_user_branch_scopes_user_member",
        "user_branch_scopes",
        ["user_id", "member_id"],
        unique=True,
        schema="peace_movement",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_user_branch_scopes_user_member",
        table_name="user_branch_scopes",
        schema="peace_movement",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_user_branch_scopes_user_id"),
        table_name="user_branch_scopes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_user_branch_scopes_member_id"),
        table_name="user_branch_scopes",
        schema="peace_movement",
    )
    op.drop_table("user_branch_scopes", schema="peace_movement")
    op.drop_index(
        op.f("ix_member_recruiter_changes_to_member_id"),
        table_name="member_recruiter_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_member_recruiter_changes_member_id"),
        table_name="member_recruiter_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_member_recruiter_changes_from_member_id"),
        table_name="member_recruiter_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_member_recruiter_changes_changed_by_user_id"),
        table_name="member_recruiter_changes",
        schema="peace_movement",
    )
    op.drop_table("member_recruiter_changes", schema="peace_movement")
    op.drop_index(
        op.f("ix_member_level_changes_to_level_id"),
        table_name="member_level_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_member_level_changes_member_id"),
        table_name="member_level_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_member_level_changes_from_level_id"),
        table_name="member_level_changes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_member_level_changes_changed_by_user_id"),
        table_name="member_level_changes",
        schema="peace_movement",
    )
    op.drop_table("member_level_changes", schema="peace_movement")
    op.drop_index(
        op.f("ix_zone_coordinator_sections_section_id"),
        table_name="zone_coordinator_sections",
        schema="peace_movement",
    )
    op.drop_table("zone_coordinator_sections", schema="peace_movement")
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_zone_coordinator_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_state_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_section_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_municipality_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_local_district_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinator_nodes_federal_district_id"),
        table_name="zone_coordinator_nodes",
        schema="peace_movement",
    )
    op.drop_table("zone_coordinator_nodes", schema="peace_movement")
    op.drop_index(
        "uq_members_current_person",
        table_name="members",
        schema="peace_movement",
        postgresql_where=sa.text(
            "status IN ('pending_validation', 'active') AND deleted_at IS NULL"
        ),
    )
    op.drop_index(
        op.f("ix_members_validated_by_user_id"), table_name="members", schema="peace_movement"
    )
    op.drop_index(op.f("ix_members_state_id"), table_name="members", schema="peace_movement")
    op.drop_index(op.f("ix_members_section_id"), table_name="members", schema="peace_movement")
    op.drop_index(
        op.f("ix_members_registered_by_user_id"), table_name="members", schema="peace_movement"
    )
    op.drop_index(
        op.f("ix_members_recruited_by_member_id"), table_name="members", schema="peace_movement"
    )
    op.drop_index(op.f("ix_members_person_id"), table_name="members", schema="peace_movement")
    op.drop_index(
        "ix_members_path", table_name="members", schema="peace_movement", postgresql_using="gist"
    )
    op.drop_index(op.f("ix_members_level_id"), table_name="members", schema="peace_movement")
    op.drop_index(op.f("ix_members_consent_id"), table_name="members", schema="peace_movement")
    op.drop_table("members", schema="peace_movement")
    op.drop_index(
        op.f("ix_zone_coordinators_user_id"),
        table_name="zone_coordinators",
        schema="peace_movement",
    )
    op.drop_index(
        op.f("ix_zone_coordinators_state_id"),
        table_name="zone_coordinators",
        schema="peace_movement",
    )
    op.drop_table("zone_coordinators", schema="peace_movement")
    op.drop_index(
        "uq_level_goals_current",
        table_name="level_goals",
        schema="peace_movement",
        postgresql_where=sa.text("valid_to IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_level_goals_state_id"), table_name="level_goals", schema="peace_movement"
    )
    op.drop_index(
        op.f("ix_level_goals_level_id"), table_name="level_goals", schema="peace_movement"
    )
    op.drop_table("level_goals", schema="peace_movement")
    op.drop_index(
        "uq_house_goals_current",
        table_name="house_goals",
        schema="peace_movement",
        postgresql_where=sa.text("valid_to IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_house_goals_state_id"), table_name="house_goals", schema="peace_movement"
    )
    op.drop_table("house_goals", schema="peace_movement")
    op.drop_index("uq_settings_singleton", table_name="settings", schema="peace_movement")
    op.drop_table("settings", schema="peace_movement")
    op.drop_table("participation_levels", schema="peace_movement")
    op.drop_index(
        "ix_network_changes_pending",
        table_name="network_changes",
        schema="peace_movement",
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.drop_table("network_changes", schema="peace_movement")
    op.execute("DROP SEQUENCE IF EXISTS peace_movement.member_tree_ids")
    op.execute("DROP SCHEMA IF EXISTS peace_movement")
    op.execute("DROP EXTENSION IF EXISTS ltree")
