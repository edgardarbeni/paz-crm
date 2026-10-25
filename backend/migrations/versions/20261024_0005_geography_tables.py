"""geography: frameworks, imports, code catalogs and imported geography (MODELO_DATOS §1)

Hand-adjusted after autogenerate: blocks id sequence (partitioned tables), and
`geography.ensure_block_partition(framework_id)` creating one LIST partition per framework.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25 01:03:22.873251+00:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import execute_script

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "block_statuses",
        sa.Column("code", sa.SmallInteger(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description_source", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "description_conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_block_statuses")),
        schema="geography",
    )
    op.create_table(
        "federal_district_types",
        sa.Column("code", sa.SmallInteger(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description_source", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "description_conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_federal_district_types")),
        schema="geography",
    )
    op.create_table(
        "geographic_frameworks",
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
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=True),
        sa.Column("source_agreement", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geographic_frameworks")),
        schema="geography",
    )
    op.create_index(
        "uq_geographic_frameworks_active",
        "geographic_frameworks",
        ["is_active"],
        unique=True,
        schema="geography",
        postgresql_where=sa.text("is_active AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_geographic_frameworks_name",
        "geographic_frameworks",
        ["name"],
        unique=True,
        schema="geography",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "locality_head_types",
        sa.Column("code", sa.SmallInteger(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description_source", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "description_conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_locality_head_types")),
        schema="geography",
    )
    op.create_table(
        "locality_types",
        sa.Column("code", sa.SmallInteger(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description_source", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "description_conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_locality_types")),
        schema="geography",
    )
    op.create_table(
        "neighborhood_types",
        sa.Column("code", sa.SmallInteger(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description_source", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "description_conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_neighborhood_types")),
        schema="geography",
    )
    op.create_table(
        "section_types",
        sa.Column("code", sa.SmallInteger(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description_source", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "description_conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_section_types")),
        schema="geography",
    )
    op.create_table(
        "import_runs",
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
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("state_code", sa.SmallInteger(), nullable=True),
        sa.Column("source_uri", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("file_sha256", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("source_srid", sa.Integer(), nullable=True),
        sa.Column("layers_loaded", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("layers_missing", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('bgd_shapefile')", name=op.f("ck_import_runs_source_kind")
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name=op.f("ck_import_runs_status")
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_import_runs_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_runs")),
        schema="geography",
    )
    op.create_index(
        op.f("ix_import_runs_framework_id"),
        "import_runs",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "electoral_regions",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("region_number", sa.SmallInteger(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_electoral_regions_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_electoral_regions_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_electoral_regions")),
        sa.UniqueConstraint(
            "framework_id", "id", name=op.f("uq_electoral_regions_framework_id_id")
        ),
        sa.UniqueConstraint(
            "framework_id",
            "region_number",
            name=op.f("uq_electoral_regions_framework_id_region_number"),
        ),
        schema="geography",
    )
    op.create_index(
        "gx_electoral_regions_geom",
        "electoral_regions",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_electoral_regions_framework_id"),
        "electoral_regions",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "import_issues",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("import_run_id", sa.Uuid(), nullable=False),
        sa.Column("layer", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("source_fid", sa.Integer(), nullable=True),
        sa.Column("natural_key", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.CheckConstraint(
            "severity IN ('error', 'warning')", name=op.f("ck_import_issues_severity")
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_import_issues_import_run_id__import_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_issues")),
        schema="geography",
    )
    op.create_index(
        op.f("ix_import_issues_import_run_id"),
        "import_issues",
        ["import_run_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "states",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("electoral_region_id", sa.Uuid(), nullable=True),
        sa.Column("state_code", sa.SmallInteger(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "electoral_region_id"],
            ["geography.electoral_regions.framework_id", "geography.electoral_regions.id"],
            name=op.f("fk_states_framework_id_electoral_region_id__electoral_regions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_states_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_states_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_states")),
        sa.UniqueConstraint("framework_id", "id", name=op.f("uq_states_framework_id_id")),
        sa.UniqueConstraint(
            "framework_id", "state_code", name=op.f("uq_states_framework_id_state_code")
        ),
        schema="geography",
    )
    op.create_index(
        "gx_states_geom",
        "states",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_states_electoral_region_id"),
        "states",
        ["electoral_region_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_states_framework_id"), "states", ["framework_id"], unique=False, schema="geography"
    )
    op.create_table(
        "federal_districts",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("district_number", sa.SmallInteger(), nullable=False),
        sa.Column("district_type_code", sa.SmallInteger(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["district_type_code"],
            ["geography.federal_district_types.code"],
            name=op.f("fk_federal_districts_district_type_code__federal_district_types"),
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "state_id"],
            ["geography.states.framework_id", "geography.states.id"],
            name=op.f("fk_federal_districts_framework_id_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_federal_districts_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_federal_districts_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_federal_districts")),
        sa.UniqueConstraint(
            "framework_id", "id", name=op.f("uq_federal_districts_framework_id_id")
        ),
        sa.UniqueConstraint(
            "state_id",
            "district_number",
            name=op.f("uq_federal_districts_state_id_district_number"),
        ),
        schema="geography",
    )
    op.create_index(
        "gx_federal_districts_geom",
        "federal_districts",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_federal_districts_framework_id"),
        "federal_districts",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_federal_districts_state_id"),
        "federal_districts",
        ["state_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "local_districts",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("district_number", sa.SmallInteger(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "state_id"],
            ["geography.states.framework_id", "geography.states.id"],
            name=op.f("fk_local_districts_framework_id_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_local_districts_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_local_districts_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_districts")),
        sa.UniqueConstraint("framework_id", "id", name=op.f("uq_local_districts_framework_id_id")),
        sa.UniqueConstraint(
            "state_id", "district_number", name=op.f("uq_local_districts_state_id_district_number")
        ),
        schema="geography",
    )
    op.create_index(
        "gx_local_districts_geom",
        "local_districts",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_local_districts_framework_id"),
        "local_districts",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_local_districts_state_id"),
        "local_districts",
        ["state_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "municipalities",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("municipality_code", sa.SmallInteger(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "state_id"],
            ["geography.states.framework_id", "geography.states.id"],
            name=op.f("fk_municipalities_framework_id_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_municipalities_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_municipalities_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_municipalities")),
        sa.UniqueConstraint("framework_id", "id", name=op.f("uq_municipalities_framework_id_id")),
        sa.UniqueConstraint(
            "state_id",
            "municipality_code",
            name=op.f("uq_municipalities_state_id_municipality_code"),
        ),
        schema="geography",
    )
    op.create_index(
        "gx_municipalities_geom",
        "municipalities",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_municipalities_framework_id"),
        "municipalities",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        "ix_municipalities_name_trgm",
        "municipalities",
        [sa.text("f_unaccent(lower(name)) gin_trgm_ops")],
        unique=False,
        schema="geography",
        postgresql_using="gin",
    )
    op.create_index(
        op.f("ix_municipalities_state_id"),
        "municipalities",
        ["state_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "localities",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("municipality_id", sa.Uuid(), nullable=False),
        sa.Column("locality_code", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("locality_type_code", sa.SmallInteger(), nullable=True),
        sa.Column("head_type_code", sa.SmallInteger(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "municipality_id"],
            ["geography.municipalities.framework_id", "geography.municipalities.id"],
            name=op.f("fk_localities_framework_id_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "state_id"],
            ["geography.states.framework_id", "geography.states.id"],
            name=op.f("fk_localities_framework_id_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_localities_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["head_type_code"],
            ["geography.locality_head_types.code"],
            name=op.f("fk_localities_head_type_code__locality_head_types"),
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_localities_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["locality_type_code"],
            ["geography.locality_types.code"],
            name=op.f("fk_localities_locality_type_code__locality_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_localities")),
        sa.UniqueConstraint("framework_id", "id", name=op.f("uq_localities_framework_id_id")),
        sa.UniqueConstraint(
            "municipality_id",
            "locality_code",
            name=op.f("uq_localities_municipality_id_locality_code"),
        ),
        schema="geography",
    )
    op.create_index(
        "gx_localities_geom",
        "localities",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_localities_framework_id"),
        "localities",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_localities_municipality_id"),
        "localities",
        ["municipality_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        "ix_localities_name_trgm",
        "localities",
        [sa.text("f_unaccent(lower(name)) gin_trgm_ops")],
        unique=False,
        schema="geography",
        postgresql_using="gin",
    )
    op.create_index(
        op.f("ix_localities_state_id"), "localities", ["state_id"], unique=False, schema="geography"
    )
    op.create_table(
        "neighborhoods",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("municipality_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
        sa.Column("neighborhood_type_code", sa.SmallInteger(), nullable=True),
        sa.Column("type_label", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column("postal_code", sqlmodel.sql.sqltypes.AutoString(length=5), nullable=True),
        sa.Column("other_postal_codes", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("representation", sa.Text(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "representation IN ('polygon', 'point')", name=op.f("ck_neighborhoods_representation")
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "municipality_id"],
            ["geography.municipalities.framework_id", "geography.municipalities.id"],
            name=op.f("fk_neighborhoods_framework_id_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "state_id"],
            ["geography.states.framework_id", "geography.states.id"],
            name=op.f("fk_neighborhoods_framework_id_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_neighborhoods_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_neighborhoods_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["neighborhood_type_code"],
            ["geography.neighborhood_types.code"],
            name=op.f("fk_neighborhoods_neighborhood_type_code__neighborhood_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_neighborhoods")),
        sa.UniqueConstraint("framework_id", "id", name=op.f("uq_neighborhoods_framework_id_id")),
        sa.UniqueConstraint(
            "state_id", "source_key", name=op.f("uq_neighborhoods_state_id_source_key")
        ),
        schema="geography",
    )
    op.create_index(
        "gx_neighborhoods_geom",
        "neighborhoods",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_neighborhoods_framework_id"),
        "neighborhoods",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_neighborhoods_municipality_id"),
        "neighborhoods",
        ["municipality_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        "ix_neighborhoods_name_trgm",
        "neighborhoods",
        [sa.text("f_unaccent(lower(name)) gin_trgm_ops")],
        unique=False,
        schema="geography",
        postgresql_using="gin",
    )
    op.create_index(
        op.f("ix_neighborhoods_state_id"),
        "neighborhoods",
        ["state_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "sections",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("section_number", sa.Integer(), nullable=False),
        sa.Column("municipality_id", sa.Uuid(), nullable=False),
        sa.Column("federal_district_id", sa.Uuid(), nullable=False),
        sa.Column("local_district_id", sa.Uuid(), nullable=False),
        sa.Column("section_type_code", sa.SmallInteger(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "federal_district_id"],
            ["geography.federal_districts.framework_id", "geography.federal_districts.id"],
            name=op.f("fk_sections_framework_id_federal_district_id__federal_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "local_district_id"],
            ["geography.local_districts.framework_id", "geography.local_districts.id"],
            name=op.f("fk_sections_framework_id_local_district_id__local_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "municipality_id"],
            ["geography.municipalities.framework_id", "geography.municipalities.id"],
            name=op.f("fk_sections_framework_id_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "state_id"],
            ["geography.states.framework_id", "geography.states.id"],
            name=op.f("fk_sections_framework_id_state_id__states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_sections_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_sections_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["section_type_code"],
            ["geography.section_types.code"],
            name=op.f("fk_sections_section_type_code__section_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint("framework_id", "id", name=op.f("uq_sections_framework_id_id")),
        sa.UniqueConstraint(
            "state_id", "section_number", name=op.f("uq_sections_state_id_section_number")
        ),
        schema="geography",
    )
    op.create_index(
        "gx_sections_geom",
        "sections",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_sections_federal_district_id"),
        "sections",
        ["federal_district_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_sections_framework_id"),
        "sections",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_sections_local_district_id"),
        "sections",
        ["local_district_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_sections_municipality_id"),
        "sections",
        ["municipality_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_sections_state_id"), "sections", ["state_id"], unique=False, schema="geography"
    )
    op.execute("CREATE SEQUENCE geography.blocks_id_seq AS bigint")
    op.create_table(
        "blocks",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("nextval('geography.blocks_id_seq')"),
            nullable=False,
        ),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("locality_id", sa.Uuid(), nullable=False),
        sa.Column("block_number", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("dispersed_raw", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column("capture_case", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "locality_id"],
            ["geography.localities.framework_id", "geography.localities.id"],
            name=op.f("fk_blocks_framework_id_locality_id__localities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "section_id"],
            ["geography.sections.framework_id", "geography.sections.id"],
            name=op.f("fk_blocks_framework_id_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_blocks_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_blocks_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["status_code"],
            ["geography.block_statuses.code"],
            name=op.f("fk_blocks_status_code__block_statuses"),
        ),
        sa.PrimaryKeyConstraint("id", "framework_id", name=op.f("pk_blocks")),
        sa.UniqueConstraint(
            "framework_id",
            "section_id",
            "locality_id",
            "block_number",
            name=op.f("uq_blocks_framework_id_section_id_locality_id_block_number"),
        ),
        schema="geography",
        postgresql_partition_by="LIST (framework_id)",
    )
    op.create_index(
        "gx_blocks_geom",
        "blocks",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_blocks_locality_id"), "blocks", ["locality_id"], unique=False, schema="geography"
    )
    op.create_index(
        op.f("ix_blocks_section_id"), "blocks", ["section_id"], unique=False, schema="geography"
    )
    op.create_table(
        "locality_sections",
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
        sa.Column("import_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("locality_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("head_type_code", sa.SmallInteger(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "locality_id"],
            ["geography.localities.framework_id", "geography.localities.id"],
            name=op.f("fk_locality_sections_framework_id_locality_id__localities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id", "section_id"],
            ["geography.sections.framework_id", "geography.sections.id"],
            name=op.f("fk_locality_sections_framework_id_section_id__sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_locality_sections_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["head_type_code"],
            ["geography.locality_head_types.code"],
            name=op.f("fk_locality_sections_head_type_code__locality_head_types"),
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["geography.import_runs.id"],
            name=op.f("fk_locality_sections_import_run_id__import_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locality_sections")),
        sa.UniqueConstraint(
            "locality_id", "section_id", name=op.f("uq_locality_sections_locality_id_section_id")
        ),
        schema="geography",
    )
    op.create_index(
        "gx_locality_sections_geom",
        "locality_sections",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_locality_sections_framework_id"),
        "locality_sections",
        ["framework_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_locality_sections_locality_id"),
        "locality_sections",
        ["locality_id"],
        unique=False,
        schema="geography",
    )
    op.create_index(
        op.f("ix_locality_sections_section_id"),
        "locality_sections",
        ["section_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "neighborhood_sections",
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
        sa.Column("neighborhood_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("overlap_ratio", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("overlap_area_m2", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.CheckConstraint(
            "source IN ('ine_catalog', 'computed')", name=op.f("ck_neighborhood_sections_source")
        ),
        sa.ForeignKeyConstraint(
            ["neighborhood_id"],
            ["geography.neighborhoods.id"],
            name=op.f("fk_neighborhood_sections_neighborhood_id__neighborhoods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_neighborhood_sections_section_id__sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "neighborhood_id", "section_id", name=op.f("pk_neighborhood_sections")
        ),
        schema="geography",
    )
    op.create_index(
        op.f("ix_neighborhood_sections_section_id"),
        "neighborhood_sections",
        ["section_id"],
        unique=False,
        schema="geography",
    )
    op.create_table(
        "section_parts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["geography.sections.id"],
            name=op.f("fk_section_parts_section_id__sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section_parts")),
        schema="geography",
    )
    op.create_index(
        "gx_section_parts_geom",
        "section_parts",
        ["geom"],
        unique=False,
        schema="geography",
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_section_parts_section_id"),
        "section_parts",
        ["section_id"],
        unique=False,
        schema="geography",
    )

    execute_script(
        """
        CREATE FUNCTION geography.ensure_block_partition(p_framework_id uuid) RETURNS text
        LANGUAGE plpgsql
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
          v_name text := 'blocks_' || replace(p_framework_id::text, '-', '');
        BEGIN
          IF to_regclass(format('geography.%I', v_name)) IS NULL THEN
            EXECUTE format(
              'CREATE TABLE geography.%I PARTITION OF geography.blocks FOR VALUES IN (%L)',
              v_name, p_framework_id
            );
          END IF;
          RETURN v_name;
        END
        $$;
        REVOKE ALL ON FUNCTION geography.ensure_block_partition(uuid) FROM PUBLIC;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS geography.ensure_block_partition(uuid)")
    op.drop_index(
        op.f("ix_section_parts_section_id"), table_name="section_parts", schema="geography"
    )
    op.drop_index(
        "gx_section_parts_geom",
        table_name="section_parts",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("section_parts", schema="geography")
    op.drop_index(
        op.f("ix_neighborhood_sections_section_id"),
        table_name="neighborhood_sections",
        schema="geography",
    )
    op.drop_table("neighborhood_sections", schema="geography")
    op.drop_index(
        op.f("ix_locality_sections_section_id"), table_name="locality_sections", schema="geography"
    )
    op.drop_index(
        op.f("ix_locality_sections_locality_id"), table_name="locality_sections", schema="geography"
    )
    op.drop_index(
        op.f("ix_locality_sections_framework_id"),
        table_name="locality_sections",
        schema="geography",
    )
    op.drop_index(
        "gx_locality_sections_geom",
        table_name="locality_sections",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("locality_sections", schema="geography")
    op.drop_index(op.f("ix_blocks_section_id"), table_name="blocks", schema="geography")
    op.drop_index(op.f("ix_blocks_locality_id"), table_name="blocks", schema="geography")
    op.drop_index(
        "gx_blocks_geom", table_name="blocks", schema="geography", postgresql_using="gist"
    )
    op.drop_table("blocks", schema="geography")
    op.execute("DROP SEQUENCE IF EXISTS geography.blocks_id_seq")
    op.drop_index(op.f("ix_sections_state_id"), table_name="sections", schema="geography")
    op.drop_index(op.f("ix_sections_municipality_id"), table_name="sections", schema="geography")
    op.drop_index(op.f("ix_sections_local_district_id"), table_name="sections", schema="geography")
    op.drop_index(op.f("ix_sections_framework_id"), table_name="sections", schema="geography")
    op.drop_index(
        op.f("ix_sections_federal_district_id"), table_name="sections", schema="geography"
    )
    op.drop_index(
        "gx_sections_geom", table_name="sections", schema="geography", postgresql_using="gist"
    )
    op.drop_table("sections", schema="geography")
    op.drop_index(op.f("ix_neighborhoods_state_id"), table_name="neighborhoods", schema="geography")
    op.drop_index(
        "ix_neighborhoods_name_trgm",
        table_name="neighborhoods",
        schema="geography",
        postgresql_using="gin",
    )
    op.drop_index(
        op.f("ix_neighborhoods_municipality_id"), table_name="neighborhoods", schema="geography"
    )
    op.drop_index(
        op.f("ix_neighborhoods_framework_id"), table_name="neighborhoods", schema="geography"
    )
    op.drop_index(
        "gx_neighborhoods_geom",
        table_name="neighborhoods",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("neighborhoods", schema="geography")
    op.drop_index(op.f("ix_localities_state_id"), table_name="localities", schema="geography")
    op.drop_index(
        "ix_localities_name_trgm",
        table_name="localities",
        schema="geography",
        postgresql_using="gin",
    )
    op.drop_index(
        op.f("ix_localities_municipality_id"), table_name="localities", schema="geography"
    )
    op.drop_index(op.f("ix_localities_framework_id"), table_name="localities", schema="geography")
    op.drop_index(
        "gx_localities_geom", table_name="localities", schema="geography", postgresql_using="gist"
    )
    op.drop_table("localities", schema="geography")
    op.drop_index(
        op.f("ix_municipalities_state_id"), table_name="municipalities", schema="geography"
    )
    op.drop_index(
        "ix_municipalities_name_trgm",
        table_name="municipalities",
        schema="geography",
        postgresql_using="gin",
    )
    op.drop_index(
        op.f("ix_municipalities_framework_id"), table_name="municipalities", schema="geography"
    )
    op.drop_index(
        "gx_municipalities_geom",
        table_name="municipalities",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("municipalities", schema="geography")
    op.drop_index(
        op.f("ix_local_districts_state_id"), table_name="local_districts", schema="geography"
    )
    op.drop_index(
        op.f("ix_local_districts_framework_id"), table_name="local_districts", schema="geography"
    )
    op.drop_index(
        "gx_local_districts_geom",
        table_name="local_districts",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("local_districts", schema="geography")
    op.drop_index(
        op.f("ix_federal_districts_state_id"), table_name="federal_districts", schema="geography"
    )
    op.drop_index(
        op.f("ix_federal_districts_framework_id"),
        table_name="federal_districts",
        schema="geography",
    )
    op.drop_index(
        "gx_federal_districts_geom",
        table_name="federal_districts",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("federal_districts", schema="geography")
    op.drop_index(op.f("ix_states_framework_id"), table_name="states", schema="geography")
    op.drop_index(op.f("ix_states_electoral_region_id"), table_name="states", schema="geography")
    op.drop_index(
        "gx_states_geom", table_name="states", schema="geography", postgresql_using="gist"
    )
    op.drop_table("states", schema="geography")
    op.drop_index(
        op.f("ix_import_issues_import_run_id"), table_name="import_issues", schema="geography"
    )
    op.drop_table("import_issues", schema="geography")
    op.drop_index(
        op.f("ix_electoral_regions_framework_id"),
        table_name="electoral_regions",
        schema="geography",
    )
    op.drop_index(
        "gx_electoral_regions_geom",
        table_name="electoral_regions",
        schema="geography",
        postgresql_using="gist",
    )
    op.drop_table("electoral_regions", schema="geography")
    op.drop_index(op.f("ix_import_runs_framework_id"), table_name="import_runs", schema="geography")
    op.drop_table("import_runs", schema="geography")
    op.drop_table("section_types", schema="geography")
    op.drop_table("neighborhood_types", schema="geography")
    op.drop_table("locality_types", schema="geography")
    op.drop_table("locality_head_types", schema="geography")
    op.drop_index(
        "uq_geographic_frameworks_name",
        table_name="geographic_frameworks",
        schema="geography",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        "uq_geographic_frameworks_active",
        table_name="geographic_frameworks",
        schema="geography",
        postgresql_where=sa.text("is_active AND deleted_at IS NULL"),
    )
    op.drop_table("geographic_frameworks", schema="geography")
    op.drop_table("federal_district_types", schema="geography")
    op.drop_table("block_statuses", schema="geography")
