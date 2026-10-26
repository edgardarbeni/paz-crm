"""people (persons, contacts, addresses, consents) and candidacies (catalogs, processes,
configuration, coalitions, nominations, formulas, history, rule overrides) — data-model.md §3-4

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25 02:08:50.943673+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office_types",
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
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("election_level", sa.Text(), nullable=False),
        sa.Column("geographic_level", sa.Text(), nullable=False),
        sa.Column("principle", sa.Text(), nullable=False),
        sa.Column("nomination_kind", sa.Text(), nullable=False),
        sa.Column("default_positions", sa.SmallInteger(), nullable=True),
        sa.Column("has_substitute", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[a-z][a-z0-9_]{1,49}$'", name=op.f("ck_office_types_code_format")
        ),
        sa.CheckConstraint(
            "election_level IN ('federal', 'local')", name=op.f("ck_office_types_election_level")
        ),
        sa.CheckConstraint(
            "geographic_level IN ('national', 'electoral_region', 'state', 'federal_district', 'local_district', 'municipality')",
            name=op.f("ck_office_types_geographic_level"),
        ),
        sa.CheckConstraint(
            "nomination_kind IN ('single', 'list', 'slate', 'member')",
            name=op.f("ck_office_types_nomination_kind"),
        ),
        sa.CheckConstraint("principle IN ('mr', 'rp')", name=op.f("ck_office_types_principle")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_office_types")),
        schema="candidacies",
    )
    op.create_index(
        "uq_office_types_code",
        "office_types",
        ["code"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "parties",
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
        sa.Column("acronym", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("is_own_party", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("color_hex", sqlmodel.sql.sqltypes.AutoString(length=7), nullable=True),
        sa.Column("logo_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.CheckConstraint(
            "color_hex IS NULL OR color_hex ~ '^#[0-9A-Fa-f]{6}$'",
            name=op.f("ck_parties_color_hex"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parties")),
        schema="candidacies",
    )
    op.create_index(
        "uq_parties_acronym",
        "parties",
        ["acronym"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "validation_rules",
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
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("default_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_rules")),
        schema="candidacies",
    )
    op.create_index(
        "uq_validation_rules_code",
        "validation_rules",
        ["code"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "persons",
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
        sa.Column("given_names", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("paternal_surname", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("maternal_surname", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True),
        sa.Column(
            "search_name",
            sa.Text(),
            sa.Computed(
                "given_names || ' ' || paternal_surname || ' ' || coalesce(maternal_surname, '')",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("sex", sqlmodel.sql.sqltypes.AutoString(length=1), nullable=True),
        sa.Column("birth_entity", sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True),
        sa.Column("curp_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("curp_hash", sa.LargeBinary(), nullable=True),
        sa.Column(
            "curp_coherence_overridden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("key_version", sa.SmallInteger(), nullable=True),
        sa.Column("purge_after", sa.Date(), nullable=True),
        sa.CheckConstraint("sex IN ('H', 'M', 'X')", name=op.f("ck_persons_sex")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_persons")),
        schema="people",
    )
    op.create_index(
        "ix_persons_search_name_trgm",
        "persons",
        [sa.literal_column("f_unaccent(lower(search_name))").label("search")],
        unique=False,
        schema="people",
        postgresql_using="gin",
        postgresql_ops={"search": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_persons_curp_hash",
        "persons",
        ["curp_hash"],
        unique=True,
        schema="people",
        postgresql_where=sa.text("deleted_at IS NULL AND curp_hash IS NOT NULL"),
    )
    op.create_table(
        "person_contacts",
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
        sa.Column("contact_type", sa.Text(), nullable=False),
        sa.Column("value_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("value_hash", sa.LargeBinary(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "contact_type IN ('mobile', 'landline', 'email')",
            name=op.f("ck_person_contacts_contact_type"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.persons.id"],
            name=op.f("fk_person_contacts_person_id__persons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_contacts")),
        schema="people",
    )
    op.create_index(
        op.f("ix_person_contacts_person_id"),
        "person_contacts",
        ["person_id"],
        unique=False,
        schema="people",
    )
    op.create_index(
        "ix_person_contacts_value_hash",
        "person_contacts",
        ["value_hash"],
        unique=False,
        schema="people",
    )
    op.create_table(
        "privacy_consents",
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
        sa.Column("notice_version", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("evidence_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('panel', 'paper', 'web')", name=op.f("ck_privacy_consents_channel")
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.persons.id"],
            name=op.f("fk_privacy_consents_person_id__persons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_privacy_consents")),
        schema="people",
    )
    op.create_index(
        op.f("ix_privacy_consents_person_id"),
        "privacy_consents",
        ["person_id"],
        unique=False,
        schema="people",
    )
    op.create_table(
        "electoral_processes",
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
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("election_year", sa.SmallInteger(), nullable=False),
        sa.Column("process_type", sa.Text(), nullable=False),
        sa.Column("election_level", sa.Text(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("election_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(election_level = 'local' AND state_id IS NOT NULL) OR (election_level = 'federal' AND state_id IS NULL)",
            name=op.f("ck_electoral_processes_state_matches_level"),
        ),
        sa.CheckConstraint(
            "election_level IN ('federal', 'local')",
            name=op.f("ck_electoral_processes_election_level"),
        ),
        sa.CheckConstraint(
            "process_type IN ('ordinary', 'extraordinary')",
            name=op.f("ck_electoral_processes_process_type"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'closed')", name=op.f("ck_electoral_processes_status")
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_electoral_processes_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_electoral_processes_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_electoral_processes")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_electoral_processes_framework_id"),
        "electoral_processes",
        ["framework_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_electoral_processes_state_id"),
        "electoral_processes",
        ["state_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_table(
        "coalitions",
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
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("coalition_kind", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "coalition_kind IN ('coalition', 'common_candidacy')",
            name=op.f("ck_coalitions_coalition_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["candidacies.electoral_processes.id"],
            name=op.f("fk_coalitions_process_id__electoral_processes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coalitions")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_coalitions_process_id"),
        "coalitions",
        ["process_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_table(
        "municipality_settings",
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
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("municipality_id", sa.Uuid(), nullable=False),
        sa.Column("election_regime", sa.Text(), nullable=False),
        sa.Column("mr_councilor_count", sa.SmallInteger(), nullable=False),
        sa.Column("rp_councilor_count", sa.SmallInteger(), nullable=False),
        sa.Column("syndic_count", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "election_regime IN ('party_based', 'normative_system')",
            name=op.f("ck_municipality_settings_election_regime"),
        ),
        sa.CheckConstraint(
            "mr_councilor_count >= 0 AND rp_councilor_count >= 0 AND syndic_count >= 0",
            name=op.f("ck_municipality_settings_counts"),
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["geography.municipalities.id"],
            name=op.f("fk_municipality_settings_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["candidacies.electoral_processes.id"],
            name=op.f("fk_municipality_settings_process_id__electoral_processes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_municipality_settings")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_municipality_settings_municipality_id"),
        "municipality_settings",
        ["municipality_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_municipality_settings_process_id"),
        "municipality_settings",
        ["process_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_municipality_settings_process_id_municipality_id",
        "municipality_settings",
        ["process_id", "municipality_id"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "process_offices",
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
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("office_type_id", sa.Uuid(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("positions", sa.SmallInteger(), nullable=True),
        sa.Column("slate_parent_office_type_id", sa.Uuid(), nullable=True),
        sa.Column("rp_method", sa.Text(), nullable=True),
        sa.Column("rp_method_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "rp_method IS NULL OR rp_method IN ('closed_list', 'best_loser', 'mixed')",
            name=op.f("ck_process_offices_rp_method"),
        ),
        sa.CheckConstraint(
            "positions IS NULL OR positions BETWEEN 1 AND 500",
            name=op.f("ck_process_offices_positions"),
        ),
        sa.ForeignKeyConstraint(
            ["office_type_id"],
            ["candidacies.office_types.id"],
            name=op.f("fk_process_offices_office_type_id__office_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["candidacies.electoral_processes.id"],
            name=op.f("fk_process_offices_process_id__electoral_processes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["slate_parent_office_type_id"],
            ["candidacies.office_types.id"],
            name=op.f("fk_process_offices_slate_parent_office_type_id__office_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_offices")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_process_offices_office_type_id"),
        "process_offices",
        ["office_type_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_process_offices_process_id"),
        "process_offices",
        ["process_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_process_offices_slate_parent_office_type_id"),
        "process_offices",
        ["slate_parent_office_type_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_process_offices_process_id_office_type_id",
        "process_offices",
        ["process_id", "office_type_id"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "process_validation_rules",
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
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("validation_rule_id", sa.Uuid(), nullable=False),
        sa.Column("office_type_id", sa.Uuid(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "severity IN ('blocking', 'warning')", name=op.f("ck_process_validation_rules_severity")
        ),
        sa.ForeignKeyConstraint(
            ["office_type_id"],
            ["candidacies.office_types.id"],
            name=op.f("fk_process_validation_rules_office_type_id__office_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["candidacies.electoral_processes.id"],
            name=op.f("fk_process_validation_rules_process_id__electoral_processes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["validation_rule_id"],
            ["candidacies.validation_rules.id"],
            name=op.f("fk_process_validation_rules_validation_rule_id__validation_rules"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_validation_rules")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_process_validation_rules_office_type_id"),
        "process_validation_rules",
        ["office_type_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_process_validation_rules_process_id"),
        "process_validation_rules",
        ["process_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_process_validation_rules_validation_rule_id"),
        "process_validation_rules",
        ["validation_rule_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_process_validation_rules_scope",
        "process_validation_rules",
        [
            "process_id",
            "validation_rule_id",
            sa.literal_column(
                "coalesce(office_type_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
        ],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "coalition_parties",
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
        sa.Column("coalition_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["coalition_id"],
            ["candidacies.coalitions.id"],
            name=op.f("fk_coalition_parties_coalition_id__coalitions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"],
            ["candidacies.parties.id"],
            name=op.f("fk_coalition_parties_party_id__parties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coalition_parties")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_coalition_parties_coalition_id"),
        "coalition_parties",
        ["coalition_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_coalition_parties_party_id"),
        "coalition_parties",
        ["party_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_coalition_parties_coalition_id_party_id",
        "coalition_parties",
        ["coalition_id", "party_id"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "nominations",
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
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("office_type_id", sa.Uuid(), nullable=False),
        sa.Column("geographic_level", sa.Text(), nullable=False),
        sa.Column("electoral_region_id", sa.Uuid(), nullable=True),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("federal_district_id", sa.Uuid(), nullable=True),
        sa.Column("local_district_id", sa.Uuid(), nullable=True),
        sa.Column("municipality_id", sa.Uuid(), nullable=True),
        sa.Column("party_id", sa.Uuid(), nullable=True),
        sa.Column("coalition_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.CheckConstraint(
            "(geographic_level = 'electoral_region' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id) = 1 AND electoral_region_id IS NOT NULL) OR (geographic_level = 'state' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id) = 1 AND state_id IS NOT NULL) OR (geographic_level = 'federal_district' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id) = 1 AND federal_district_id IS NOT NULL) OR (geographic_level = 'local_district' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id) = 1 AND local_district_id IS NOT NULL) OR (geographic_level = 'municipality' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id) = 1 AND municipality_id IS NOT NULL) OR (geographic_level = 'national' AND num_nonnulls(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id) = 0)",
            name=op.f("ck_nominations_geography_matches_level"),
        ),
        sa.CheckConstraint(
            "geographic_level IN ('national', 'electoral_region', 'state', 'federal_district', 'local_district', 'municipality')",
            name=op.f("ck_nominations_geographic_level"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'cancelled')",
            name=op.f("ck_nominations_status"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(party_id, coalition_id) = 1", name=op.f("ck_nominations_one_nominator")
        ),
        sa.ForeignKeyConstraint(
            ["coalition_id"],
            ["candidacies.coalitions.id"],
            name=op.f("fk_nominations_coalition_id__coalitions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["electoral_region_id"],
            ["geography.electoral_regions.id"],
            name=op.f("fk_nominations_electoral_region_id__electoral_regions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["federal_district_id"],
            ["geography.federal_districts.id"],
            name=op.f("fk_nominations_federal_district_id__federal_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["local_district_id"],
            ["geography.local_districts.id"],
            name=op.f("fk_nominations_local_district_id__local_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["geography.municipalities.id"],
            name=op.f("fk_nominations_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["office_type_id"],
            ["candidacies.office_types.id"],
            name=op.f("fk_nominations_office_type_id__office_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"],
            ["candidacies.parties.id"],
            name=op.f("fk_nominations_party_id__parties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["candidacies.electoral_processes.id"],
            name=op.f("fk_nominations_process_id__electoral_processes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_nominations_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nominations")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_coalition_id"),
        "nominations",
        ["coalition_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_electoral_region_id"),
        "nominations",
        ["electoral_region_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_federal_district_id"),
        "nominations",
        ["federal_district_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_local_district_id"),
        "nominations",
        ["local_district_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_municipality_id"),
        "nominations",
        ["municipality_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_office_type_id"),
        "nominations",
        ["office_type_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_party_id"),
        "nominations",
        ["party_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_process_id"),
        "nominations",
        ["process_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_nominations_state_id"),
        "nominations",
        ["state_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_nominations_active",
        "nominations",
        [
            "process_id",
            "office_type_id",
            sa.literal_column(
                "coalesce(electoral_region_id, state_id, federal_district_id, local_district_id, municipality_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.literal_column("coalesce(party_id, coalition_id)"),
        ],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL AND status <> 'cancelled'"),
    )
    op.create_table(
        "person_addresses",
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
        sa.Column("address_type", sa.Text(), nullable=False),
        sa.Column("address_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("postal_code", sqlmodel.sql.sqltypes.AutoString(length=5), nullable=True),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("municipality_id", sa.Uuid(), nullable=True),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        sa.Column("neighborhood_id", sa.Uuid(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint(
            "address_type IN ('home', 'work', 'other')",
            name=op.f("ck_person_addresses_address_type"),
        ),
        sa.ForeignKeyConstraint(
            ["locality_id"],
            ["geography.localities.id"],
            name=op.f("fk_person_addresses_locality_id__localities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["geography.municipalities.id"],
            name=op.f("fk_person_addresses_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["neighborhood_id"],
            ["geography.neighborhoods.id"],
            name=op.f("fk_person_addresses_neighborhood_id__neighborhoods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.persons.id"],
            name=op.f("fk_person_addresses_person_id__persons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_person_addresses_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["geography.states.id"],
            name=op.f("fk_person_addresses_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_addresses")),
        schema="people",
    )
    op.create_index(
        op.f("ix_person_addresses_person_id"),
        "person_addresses",
        ["person_id"],
        unique=False,
        schema="people",
    )
    op.create_index(
        "ix_person_addresses_section_id",
        "person_addresses",
        ["section_id"],
        unique=False,
        schema="people",
    )
    op.create_table(
        "formulas",
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
        sa.Column("nomination_id", sa.Uuid(), nullable=False),
        sa.Column("office_type_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("origin_party_id", sa.Uuid(), nullable=True),
        sa.Column("replaces_formula_id", sa.Uuid(), nullable=True),
        sa.Column(
            "substitution_reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True
        ),
        sa.CheckConstraint(
            "status IN ('aspirant', 'registered', 'approved', 'substituted', 'cancelled')",
            name=op.f("ck_formulas_status"),
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 500", name=op.f("ck_formulas_position")),
        sa.ForeignKeyConstraint(
            ["nomination_id"],
            ["candidacies.nominations.id"],
            name=op.f("fk_formulas_nomination_id__nominations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["office_type_id"],
            ["candidacies.office_types.id"],
            name=op.f("fk_formulas_office_type_id__office_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_party_id"],
            ["candidacies.parties.id"],
            name=op.f("fk_formulas_origin_party_id__parties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replaces_formula_id"],
            ["candidacies.formulas.id"],
            name=op.f("fk_formulas_replaces_formula_id__formulas"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formulas")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_formulas_nomination_id"),
        "formulas",
        ["nomination_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_formulas_office_type_id"),
        "formulas",
        ["office_type_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_formulas_origin_party_id"),
        "formulas",
        ["origin_party_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_formulas_replaces_formula_id"),
        "formulas",
        ["replaces_formula_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_formulas_active_position",
        "formulas",
        ["nomination_id", "office_type_id", "position"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text(
            "deleted_at IS NULL AND status NOT IN ('substituted', 'cancelled')"
        ),
    )
    op.create_table(
        "formula_members",
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
        sa.Column("formula_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("member_role", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "member_role IN ('owner', 'substitute')", name=op.f("ck_formula_members_member_role")
        ),
        sa.ForeignKeyConstraint(
            ["formula_id"],
            ["candidacies.formulas.id"],
            name=op.f("fk_formula_members_formula_id__formulas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.persons.id"],
            name=op.f("fk_formula_members_person_id__persons"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["candidacies.electoral_processes.id"],
            name=op.f("fk_formula_members_process_id__electoral_processes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formula_members")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_formula_members_formula_id"),
        "formula_members",
        ["formula_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "ix_formula_members_process_id_person_id",
        "formula_members",
        ["process_id", "person_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        "uq_formula_members_formula_id_member_role",
        "formula_members",
        ["formula_id", "member_role"],
        unique=True,
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "formula_status_history",
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
        sa.Column("formula_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["identity.users.id"],
            name=op.f("fk_formula_status_history_changed_by_user_id__users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["formula_id"],
            ["candidacies.formulas.id"],
            name=op.f("fk_formula_status_history_formula_id__formulas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formula_status_history")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_formula_status_history_formula_id"),
        "formula_status_history",
        ["formula_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_table(
        "rule_overrides",
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
        sa.Column("nomination_id", sa.Uuid(), nullable=False),
        sa.Column("formula_id", sa.Uuid(), nullable=True),
        sa.Column("validation_rule_id", sa.Uuid(), nullable=False),
        sa.Column("overridden_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["formula_id"],
            ["candidacies.formulas.id"],
            name=op.f("fk_rule_overrides_formula_id__formulas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["nomination_id"],
            ["candidacies.nominations.id"],
            name=op.f("fk_rule_overrides_nomination_id__nominations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["overridden_by_user_id"],
            ["identity.users.id"],
            name=op.f("fk_rule_overrides_overridden_by_user_id__users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["validation_rule_id"],
            ["candidacies.validation_rules.id"],
            name=op.f("fk_rule_overrides_validation_rule_id__validation_rules"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_overrides")),
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_rule_overrides_formula_id"),
        "rule_overrides",
        ["formula_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_rule_overrides_nomination_id"),
        "rule_overrides",
        ["nomination_id"],
        unique=False,
        schema="candidacies",
    )
    op.create_index(
        op.f("ix_rule_overrides_validation_rule_id"),
        "rule_overrides",
        ["validation_rule_id"],
        unique=False,
        schema="candidacies",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_rule_overrides_validation_rule_id"),
        table_name="rule_overrides",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_rule_overrides_nomination_id"), table_name="rule_overrides", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_rule_overrides_formula_id"), table_name="rule_overrides", schema="candidacies"
    )
    op.drop_table("rule_overrides", schema="candidacies")
    op.drop_index(
        op.f("ix_formula_status_history_formula_id"),
        table_name="formula_status_history",
        schema="candidacies",
    )
    op.drop_table("formula_status_history", schema="candidacies")
    op.drop_index(
        "uq_formula_members_formula_id_member_role",
        table_name="formula_members",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        "ix_formula_members_process_id_person_id",
        table_name="formula_members",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_formula_members_formula_id"), table_name="formula_members", schema="candidacies"
    )
    op.drop_table("formula_members", schema="candidacies")
    op.drop_index(
        "uq_formulas_active_position",
        table_name="formulas",
        schema="candidacies",
        postgresql_where=sa.text(
            "deleted_at IS NULL AND status NOT IN ('substituted', 'cancelled')"
        ),
    )
    op.drop_index(
        op.f("ix_formulas_replaces_formula_id"), table_name="formulas", schema="candidacies"
    )
    op.drop_index(op.f("ix_formulas_origin_party_id"), table_name="formulas", schema="candidacies")
    op.drop_index(op.f("ix_formulas_office_type_id"), table_name="formulas", schema="candidacies")
    op.drop_index(op.f("ix_formulas_nomination_id"), table_name="formulas", schema="candidacies")
    op.drop_table("formulas", schema="candidacies")
    op.drop_index("ix_person_addresses_section_id", table_name="person_addresses", schema="people")
    op.drop_index(
        op.f("ix_person_addresses_person_id"), table_name="person_addresses", schema="people"
    )
    op.drop_table("person_addresses", schema="people")
    op.drop_index(
        "uq_nominations_active",
        table_name="nominations",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL AND status <> 'cancelled'"),
    )
    op.drop_index(op.f("ix_nominations_state_id"), table_name="nominations", schema="candidacies")
    op.drop_index(op.f("ix_nominations_process_id"), table_name="nominations", schema="candidacies")
    op.drop_index(op.f("ix_nominations_party_id"), table_name="nominations", schema="candidacies")
    op.drop_index(
        op.f("ix_nominations_office_type_id"), table_name="nominations", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_nominations_municipality_id"), table_name="nominations", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_nominations_local_district_id"), table_name="nominations", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_nominations_federal_district_id"), table_name="nominations", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_nominations_electoral_region_id"), table_name="nominations", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_nominations_coalition_id"), table_name="nominations", schema="candidacies"
    )
    op.drop_table("nominations", schema="candidacies")
    op.drop_index(
        "uq_coalition_parties_coalition_id_party_id",
        table_name="coalition_parties",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_coalition_parties_party_id"), table_name="coalition_parties", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_coalition_parties_coalition_id"),
        table_name="coalition_parties",
        schema="candidacies",
    )
    op.drop_table("coalition_parties", schema="candidacies")
    op.drop_index(
        "uq_process_validation_rules_scope",
        table_name="process_validation_rules",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_process_validation_rules_validation_rule_id"),
        table_name="process_validation_rules",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_process_validation_rules_process_id"),
        table_name="process_validation_rules",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_process_validation_rules_office_type_id"),
        table_name="process_validation_rules",
        schema="candidacies",
    )
    op.drop_table("process_validation_rules", schema="candidacies")
    op.drop_index(
        "uq_process_offices_process_id_office_type_id",
        table_name="process_offices",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_process_offices_slate_parent_office_type_id"),
        table_name="process_offices",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_process_offices_process_id"), table_name="process_offices", schema="candidacies"
    )
    op.drop_index(
        op.f("ix_process_offices_office_type_id"),
        table_name="process_offices",
        schema="candidacies",
    )
    op.drop_table("process_offices", schema="candidacies")
    op.drop_index(
        "uq_municipality_settings_process_id_municipality_id",
        table_name="municipality_settings",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_municipality_settings_process_id"),
        table_name="municipality_settings",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_municipality_settings_municipality_id"),
        table_name="municipality_settings",
        schema="candidacies",
    )
    op.drop_table("municipality_settings", schema="candidacies")
    op.drop_index(op.f("ix_coalitions_process_id"), table_name="coalitions", schema="candidacies")
    op.drop_table("coalitions", schema="candidacies")
    op.drop_index(
        op.f("ix_electoral_processes_state_id"),
        table_name="electoral_processes",
        schema="candidacies",
    )
    op.drop_index(
        op.f("ix_electoral_processes_framework_id"),
        table_name="electoral_processes",
        schema="candidacies",
    )
    op.drop_table("electoral_processes", schema="candidacies")
    op.drop_index(
        op.f("ix_privacy_consents_person_id"), table_name="privacy_consents", schema="people"
    )
    op.drop_table("privacy_consents", schema="people")
    op.drop_index("ix_person_contacts_value_hash", table_name="person_contacts", schema="people")
    op.drop_index(
        op.f("ix_person_contacts_person_id"), table_name="person_contacts", schema="people"
    )
    op.drop_table("person_contacts", schema="people")
    op.drop_index(
        "uq_persons_curp_hash",
        table_name="persons",
        schema="people",
        postgresql_where=sa.text("deleted_at IS NULL AND curp_hash IS NOT NULL"),
    )
    op.drop_index(
        "ix_persons_search_name_trgm",
        table_name="persons",
        schema="people",
        postgresql_using="gin",
        postgresql_ops={"search": "gin_trgm_ops"},
    )
    op.drop_table("persons", schema="people")
    op.drop_index(
        "uq_validation_rules_code",
        table_name="validation_rules",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("validation_rules", schema="candidacies")
    op.drop_index(
        "uq_parties_acronym",
        table_name="parties",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("parties", schema="candidacies")
    op.drop_index(
        "uq_office_types_code",
        table_name="office_types",
        schema="candidacies",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("office_types", schema="candidacies")
