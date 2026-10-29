"""Geography tables (schema `geography`).
See docs/reference/data-model.md §1, D-01..D-20, D-57..D-59.

- Imported rows are read-only for the application (D-04): they carry `import_run_id` and
  `is_active` instead of soft delete, and are not audited row by row (D-36); each run is.
- Parent references use composite foreign keys ``(framework_id, parent_id)`` so a row can
  never point to a parent from another framework (docs/reference/data-model.md §1, D-41 point 6).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.db.base import BusinessTable, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "geography"
TZ = DateTime(timezone=True)


def _geom(kind: str, *, nullable: bool = False) -> Any:
    return Field(
        default=None if nullable else ...,
        sa_type=Geometry(kind, srid=4326, spatial_index=False),
        nullable=nullable,
    )


def _gist(table: str) -> Index:
    return Index(f"gx_{table}_geom", "geom", postgresql_using="gist")


def _trigram(table: str) -> Index:
    """Accent/case-insensitive fuzzy search on names (pg_trgm over f_unaccent(lower(name)))."""
    return Index(
        f"ix_{table}_name_trgm",
        func.f_unaccent(func.lower(literal_column("name"))).label("name_search"),
        postgresql_using="gin",
        postgresql_ops={"name_search": "gin_trgm_ops"},
    )


def _fk(table: str, *, ondelete: str = "RESTRICT") -> Any:
    return Field(  # type: ignore[call-overload]
        foreign_key=f"{SCHEMA}.{table}.id", ondelete=ondelete, index=True
    )


def _parent(*, nullable: bool = False) -> Any:
    """Parent node id; integrity comes from `_same_framework(...)` in __table_args__."""
    return Field(default=None if nullable else ..., nullable=nullable, index=True)


def _same_framework(column: str, parent_table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["framework_id", column],
        [f"{SCHEMA}.{parent_table}.framework_id", f"{SCHEMA}.{parent_table}.id"],
        ondelete="RESTRICT",
    )


def _framework_id_unique() -> UniqueConstraint:
    """Target of children's composite foreign keys."""
    return UniqueConstraint("framework_id", "id")


def _code(catalog: str) -> Any:
    return Field(
        default=None, sa_type=SmallInteger, foreign_key=f"{SCHEMA}.{catalog}.code", nullable=True
    )


# --- frameworks and imports ------------------------------------------------------------------


class GeographicFramework(BusinessTable, table=True):
    """A versioned INE geography ("marco geográfico", D-01). One is active at a time."""

    __tablename__ = "geographic_frameworks"
    __table_args__ = (
        Index(
            "uq_geographic_frameworks_name",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_geographic_frameworks_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active AND deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    name: str = Field(max_length=100)
    cutoff_date: date | None = Field(default=None, sa_type=Date)
    source_agreement: str | None = Field(default=None, max_length=200)
    is_active: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    activated_at: datetime | None = Field(default=None, sa_type=TZ)
    notes: str | None = None


class ImportStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ImportRun(UUIDPrimaryKeyMixin, TimestampMixin, table=True):
    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status"),
        CheckConstraint("source_kind IN ('bgd_shapefile')", name="source_kind"),
        {"schema": SCHEMA},
    )
    __audit__: ClassVar[bool] = False  # one explicit "geo_import" audit entry per run (D-36)

    framework_id: uuid.UUID = _fk("geographic_frameworks")
    source_kind: str = Field(default="bgd_shapefile", sa_type=Text)
    state_code: int | None = Field(default=None, sa_type=SmallInteger)
    source_uri: str
    file_sha256: str | None = Field(default=None, max_length=64)
    source_srid: int | None = Field(default=None, sa_type=Integer)
    layers_loaded: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    layers_missing: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    dry_run: bool = False
    status: str = Field(default=ImportStatus.RUNNING, sa_type=Text)
    counts: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    warning_count: int = 0
    error_count: int = 0
    message: str | None = None
    started_at: datetime = Field(sa_type=TZ)
    finished_at: datetime | None = Field(default=None, sa_type=TZ)
    triggered_by: str | None = Field(default=None, max_length=200)


class ImportIssue(SQLModel, table=True):
    """Per-record warning or error of an import (bigint PK, D-03)."""

    __tablename__ = "import_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('error', 'warning')", name="severity"),
        {"schema": SCHEMA},
    )
    __audit__: ClassVar[bool] = False

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    import_run_id: uuid.UUID = _fk("import_runs", ondelete="CASCADE")
    layer: str = Field(max_length=50)
    source_fid: int | None = Field(default=None, sa_type=Integer)
    natural_key: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    severity: str = Field(sa_type=Text)
    code: str = Field(max_length=50)
    message: str
    created_at: datetime | None = Field(
        default=None, sa_type=TZ, sa_column_kwargs={"server_default": text("now()")}
    )


# --- code catalogs (D-15, D-59) --------------------------------------------------------------


class _CodeCatalog(SQLModel):
    __audit__: ClassVar[bool] = False

    code: int = Field(primary_key=True, sa_type=SmallInteger)
    description: str | None = None
    description_source: str | None = None
    # True once two pieces of evidence disagree (e.g. two states): the description stays empty
    # and is never filled automatically again (D-62).
    description_conflict: bool = Field(
        default=False, sa_column_kwargs={"server_default": text("false")}
    )


class SectionType(_CodeCatalog, table=True):
    __tablename__ = "section_types"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}


class FederalDistrictType(_CodeCatalog, table=True):
    __tablename__ = "federal_district_types"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}


class BlockStatus(_CodeCatalog, table=True):
    __tablename__ = "block_statuses"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}


class LocalityType(_CodeCatalog, table=True):
    __tablename__ = "locality_types"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}


class LocalityHeadType(_CodeCatalog, table=True):
    __tablename__ = "locality_head_types"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}


class NeighborhoodType(_CodeCatalog, table=True):
    __tablename__ = "neighborhood_types"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}


CODE_CATALOGS: tuple[type[_CodeCatalog], ...] = (
    SectionType,
    FederalDistrictType,
    BlockStatus,
    LocalityType,
    LocalityHeadType,
    NeighborhoodType,
)


# --- imported geography ----------------------------------------------------------------------


class _Imported(SQLModel):
    __audit__: ClassVar[bool] = False

    import_run_id: uuid.UUID | None = Field(
        default=None, foreign_key=f"{SCHEMA}.import_runs.id", ondelete="SET NULL"
    )
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})


class _GeoNode(_Imported, TimestampMixin, UUIDPrimaryKeyMixin):
    """UUIDv7 PK (referenced by candidacies, scopes and addresses, D-03) + import metadata."""

    framework_id: uuid.UUID = _fk("geographic_frameworks")


class ElectoralRegion(_GeoNode, table=True):
    __tablename__ = "electoral_regions"
    __table_args__ = (
        UniqueConstraint("framework_id", "region_number"),
        _framework_id_unique(),
        _gist("electoral_regions"),
        {"schema": SCHEMA},
    )

    region_number: int = Field(sa_type=SmallInteger)
    geom: Any = _geom("MULTIPOLYGON", nullable=True)


class State(_GeoNode, table=True):
    __tablename__ = "states"
    __table_args__ = (
        UniqueConstraint("framework_id", "state_code"),
        _framework_id_unique(),
        _same_framework("electoral_region_id", "electoral_regions"),
        _gist("states"),
        {"schema": SCHEMA},
    )

    electoral_region_id: uuid.UUID | None = _parent(nullable=True)
    state_code: int = Field(sa_type=SmallInteger)
    name: str = Field(max_length=100)
    source_id: int | None = Field(default=None, sa_type=Integer)
    geom: Any = _geom("MULTIPOLYGON")
    # D-80: simplified copies for low-zoom tiles (geom_low z <= 6, geom_mid z 7-9).
    geom_low: Any = _geom("MULTIPOLYGON", nullable=True)
    geom_mid: Any = _geom("MULTIPOLYGON", nullable=True)


class Municipality(_GeoNode, table=True):
    __tablename__ = "municipalities"
    __table_args__ = (
        UniqueConstraint("state_id", "municipality_code"),
        _framework_id_unique(),
        _same_framework("state_id", "states"),
        _gist("municipalities"),
        _trigram("municipalities"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID = _parent()
    municipality_code: int = Field(sa_type=SmallInteger)
    name: str = Field(max_length=150)
    source_id: int | None = Field(default=None, sa_type=Integer)
    geom: Any = _geom("MULTIPOLYGON")
    # D-80: simplified copies for low-zoom tiles (geom_low z <= 6, geom_mid z 7-9).
    geom_low: Any = _geom("MULTIPOLYGON", nullable=True)
    geom_mid: Any = _geom("MULTIPOLYGON", nullable=True)


class FederalDistrict(_GeoNode, table=True):
    __tablename__ = "federal_districts"
    __table_args__ = (
        UniqueConstraint("state_id", "district_number"),
        _framework_id_unique(),
        _same_framework("state_id", "states"),
        _gist("federal_districts"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID = _parent()
    district_number: int = Field(sa_type=SmallInteger)
    district_type_code: int | None = _code("federal_district_types")
    source_id: int | None = Field(default=None, sa_type=Integer)
    geom: Any = _geom("MULTIPOLYGON")
    # D-80: simplified copies for low-zoom tiles (geom_low z <= 6, geom_mid z 7-9).
    geom_low: Any = _geom("MULTIPOLYGON", nullable=True)
    geom_mid: Any = _geom("MULTIPOLYGON", nullable=True)


class LocalDistrict(_GeoNode, table=True):
    __tablename__ = "local_districts"
    __table_args__ = (
        UniqueConstraint("state_id", "district_number"),
        _framework_id_unique(),
        _same_framework("state_id", "states"),
        _gist("local_districts"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID = _parent()
    district_number: int = Field(sa_type=SmallInteger)
    source_id: int | None = Field(default=None, sa_type=Integer)
    geom: Any = _geom("MULTIPOLYGON")
    # D-80: simplified copies for low-zoom tiles (geom_low z <= 6, geom_mid z 7-9).
    geom_low: Any = _geom("MULTIPOLYGON", nullable=True)
    geom_mid: Any = _geom("MULTIPOLYGON", nullable=True)


class Section(_GeoNode, table=True):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("state_id", "section_number"),
        _framework_id_unique(),
        _same_framework("state_id", "states"),
        _same_framework("municipality_id", "municipalities"),
        _same_framework("federal_district_id", "federal_districts"),
        _same_framework("local_district_id", "local_districts"),
        _gist("sections"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID = _parent()
    section_number: int = Field(sa_type=Integer)
    municipality_id: uuid.UUID = _parent()
    federal_district_id: uuid.UUID = _parent()
    local_district_id: uuid.UUID = _parent()
    section_type_code: int | None = _code("section_types")
    source_id: int | None = Field(default=None, sa_type=Integer)
    geom: Any = _geom("MULTIPOLYGON")
    # D-80: simplified copy for low-zoom tiles (z 7-9).
    geom_mid: Any = _geom("MULTIPOLYGON", nullable=True)


class SectionPart(SQLModel, table=True):
    """Sections split with ST_Subdivide so point-in-polygon stays fast (D-19)."""

    __tablename__ = "section_parts"
    __table_args__ = (_gist("section_parts"), {"schema": SCHEMA})
    __audit__: ClassVar[bool] = False

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    section_id: uuid.UUID = _fk("sections", ondelete="CASCADE")
    geom: Any = _geom("POLYGON")


class Locality(_GeoNode, table=True):
    __tablename__ = "localities"
    __table_args__ = (
        UniqueConstraint("municipality_id", "locality_code"),
        _framework_id_unique(),
        _same_framework("state_id", "states"),
        _same_framework("municipality_id", "municipalities"),
        _gist("localities"),
        _trigram("localities"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID = _parent()
    municipality_id: uuid.UUID = _parent()
    locality_code: int = Field(sa_type=Integer)
    name: str | None = Field(default=None, max_length=200)
    locality_type_code: int | None = _code("locality_types")
    head_type_code: int | None = _code("locality_head_types")
    geom: Any = _geom("MULTIPOLYGON", nullable=True)


class LocalitySection(_Imported, TimestampMixin, table=True):
    """LOCALIDAD points: the part of a locality that falls in a section (bigint PK, D-11)."""

    __tablename__ = "locality_sections"
    __table_args__ = (
        UniqueConstraint("locality_id", "section_id"),
        _same_framework("locality_id", "localities"),
        _same_framework("section_id", "sections"),
        _gist("locality_sections"),
        {"schema": SCHEMA},
    )

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    framework_id: uuid.UUID = _fk("geographic_frameworks")
    locality_id: uuid.UUID = _parent()
    section_id: uuid.UUID = _parent()
    name: str | None = Field(default=None, max_length=200)
    status_code: int | None = Field(default=None, sa_type=SmallInteger)
    head_type_code: int | None = _code("locality_head_types")
    source_id: int | None = Field(default=None, sa_type=Integer)
    geom: Any = _geom("POINT")


class Block(_Imported, TimestampMixin, table=True):
    """Manzanas: 2.5 M per framework, LIST-partitioned by framework (D-14), bigint PK (D-03).
    Partitions are created per framework by `geography.ensure_block_partition()`."""

    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("framework_id", "section_id", "locality_id", "block_number"),
        _same_framework("section_id", "sections"),
        _same_framework("locality_id", "localities"),
        _gist("blocks"),
        {"schema": SCHEMA, "postgresql_partition_by": "LIST (framework_id)"},
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_type=BigInteger,
        sa_column_kwargs={"server_default": text("nextval('geography.blocks_id_seq')")},
    )
    framework_id: uuid.UUID = Field(
        primary_key=True, foreign_key=f"{SCHEMA}.geographic_frameworks.id", ondelete="RESTRICT"
    )
    section_id: uuid.UUID = _parent()
    locality_id: uuid.UUID = _parent()
    block_number: int = Field(sa_type=Integer)
    status_code: int | None = _code("block_statuses")
    dispersed_raw: str | None = Field(default=None, max_length=10)
    capture_case: int | None = Field(default=None, sa_type=Integer)
    source_id: int | None = Field(default=None, sa_type=BigInteger)
    geom: Any = _geom("MULTIPOLYGON")


class NeighborhoodRepresentation(StrEnum):
    POLYGON = "polygon"
    POINT = "point"


class Neighborhood(_GeoNode, table=True):
    __tablename__ = "neighborhoods"
    __table_args__ = (
        UniqueConstraint("state_id", "source_key"),
        _framework_id_unique(),
        _same_framework("state_id", "states"),
        _same_framework("municipality_id", "municipalities"),
        CheckConstraint("representation IN ('polygon', 'point')", name="representation"),
        _gist("neighborhoods"),
        _trigram("neighborhoods"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID = _parent()
    municipality_id: uuid.UUID = _parent()
    source_key: str = Field(max_length=40)  # BGD COLONIA.ID (D-58)
    name: str | None = Field(default=None, max_length=250)
    neighborhood_type_code: int | None = _code("neighborhood_types")
    # Official colonia type text from the INE catalog, per colonia (D-62): CLASIFICAC alone is
    # not a reliable code nationally.
    type_label: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=5)
    other_postal_codes: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    representation: str = Field(default=NeighborhoodRepresentation.POLYGON, sa_type=Text)
    geom: Any = _geom("GEOMETRY", nullable=True)


class NeighborhoodSource(StrEnum):
    INE_CATALOG = "ine_catalog"
    COMPUTED = "computed"


class NeighborhoodSection(TimestampMixin, table=True):
    """Colonia ↔ sección, N:M (D-57)."""

    __tablename__ = "neighborhood_sections"
    __table_args__ = (
        CheckConstraint("source IN ('ine_catalog', 'computed')", name="source"),
        {"schema": SCHEMA},
    )
    __audit__: ClassVar[bool] = False

    neighborhood_id: uuid.UUID = Field(
        primary_key=True, foreign_key=f"{SCHEMA}.neighborhoods.id", ondelete="CASCADE"
    )
    section_id: uuid.UUID = Field(
        primary_key=True, foreign_key=f"{SCHEMA}.sections.id", ondelete="CASCADE", index=True
    )
    source: str = Field(sa_type=Text)
    overlap_ratio: Decimal | None = Field(default=None, sa_type=Numeric(6, 5))
    overlap_area_m2: Decimal | None = Field(default=None, sa_type=Numeric(14, 2))
