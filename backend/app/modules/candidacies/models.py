"""Candidacies (schema `candidacies`). See docs/reference/data-model.md §4 and D-21..D-29.

One structure for every office: a *nomination* (postulación) has a geography and a nominator
(party or coalition); each *formula* is one position of it, always owner + substitute.
Composition (which offices and how many positions) comes from configuration, so new offices
never require migrations (CLAUDE.md §Candidaturas, D-23).
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import CheckConstraint, Date, DateTime, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.db.base import BusinessTable

SCHEMA = "candidacies"
TZ = DateTime(timezone=True)


def _check_in(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value.value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


def _fk(
    table: str, *, ondelete: str = "RESTRICT", nullable: bool = False, schema: str = SCHEMA
) -> Any:
    return Field(  # type: ignore[call-overload]
        default=None if nullable else ...,
        foreign_key=f"{schema}.{table}.id",
        ondelete=ondelete,
        nullable=nullable,
        index=True,
    )


def _alive_unique(name: str, *columns: str) -> Index:
    return Index(name, *columns, unique=True, postgresql_where=text("deleted_at IS NULL"))


class ElectionLevel(StrEnum):
    FEDERAL = "federal"
    LOCAL = "local"


class GeographicLevel(StrEnum):
    NATIONAL = "national"
    ELECTORAL_REGION = "electoral_region"
    STATE = "state"
    FEDERAL_DISTRICT = "federal_district"
    LOCAL_DISTRICT = "local_district"
    MUNICIPALITY = "municipality"


GEO_COLUMNS: dict[GeographicLevel, str] = {
    GeographicLevel.ELECTORAL_REGION: "electoral_region_id",
    GeographicLevel.STATE: "state_id",
    GeographicLevel.FEDERAL_DISTRICT: "federal_district_id",
    GeographicLevel.LOCAL_DISTRICT: "local_district_id",
    GeographicLevel.MUNICIPALITY: "municipality_id",
}


class Principle(StrEnum):
    MR = "mr"
    RP = "rp"


class NominationKind(StrEnum):
    SINGLE = "single"  # one formula (governor, DF/DL by MR, presidency, separate syndic)
    LIST = "list"  # ordered positions (RP lists, senate pair)
    SLATE = "slate"  # head + member offices (planilla municipal, alcaldía CDMX)
    MEMBER = "member"  # only inside a slate (regidurías, concejalías)


class RpMethod(StrEnum):
    CLOSED_LIST = "closed_list"
    BEST_LOSER = "best_loser"
    MIXED = "mixed"


class ProcessType(StrEnum):
    ORDINARY = "ordinary"
    EXTRAORDINARY = "extraordinary"


class ProcessStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class ElectionRegime(StrEnum):
    PARTY_BASED = "party_based"
    NORMATIVE_SYSTEM = "normative_system"  # sistemas normativos internos (D-26)


class NominationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    CANCELLED = "cancelled"


class FormulaStatus(StrEnum):
    ASPIRANT = "aspirant"
    REGISTERED = "registered"
    APPROVED = "approved"
    SUBSTITUTED = "substituted"
    CANCELLED = "cancelled"


ACTIVE_FORMULA = ("aspirant", "registered", "approved")


class MemberRole(StrEnum):
    OWNER = "owner"
    SUBSTITUTE = "substitute"


class Severity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


class CoalitionKind(StrEnum):
    COALITION = "coalition"
    COMMON_CANDIDACY = "common_candidacy"


# --- catalogs --------------------------------------------------------------------------------


class Party(BusinessTable, table=True):
    __tablename__ = "parties"
    __table_args__ = (
        _alive_unique("uq_parties_acronym", "acronym"),
        CheckConstraint("color_hex IS NULL OR color_hex ~ '^#[0-9A-Fa-f]{6}$'", name="color_hex"),
        {"schema": SCHEMA},
    )

    acronym: str = Field(max_length=20)
    name: str = Field(max_length=150)
    is_own_party: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    color_hex: str | None = Field(default=None, max_length=7)
    logo_uri: str | None = Field(default=None, max_length=500)


class OfficeType(BusinessTable, table=True):
    __tablename__ = "office_types"
    __table_args__ = (
        _alive_unique("uq_office_types_code", "code"),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,49}$'", name="code_format"),
        _check_in("election_level", ElectionLevel, "election_level"),
        _check_in("geographic_level", GeographicLevel, "geographic_level"),
        _check_in("principle", Principle, "principle"),
        _check_in("nomination_kind", NominationKind, "nomination_kind"),
        {"schema": SCHEMA},
    )

    code: str = Field(max_length=50)
    name: str = Field(max_length=150)
    election_level: str = Field(sa_type=Text)
    geographic_level: str = Field(sa_type=Text)
    principle: str = Field(sa_type=Text)
    nomination_kind: str = Field(sa_type=Text)
    default_positions: int | None = Field(default=None, sa_type=SmallInteger)
    has_substitute: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})
    sort_order: int = Field(default=100, sa_type=SmallInteger)


class ValidationRule(BusinessTable, table=True):
    __tablename__ = "validation_rules"
    __table_args__ = (_alive_unique("uq_validation_rules_code", "code"), {"schema": SCHEMA})

    code: str = Field(max_length=50)
    name: str = Field(max_length=150)
    description: str
    default_params: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)


# --- processes and configuration (D-23..D-26, D-28) ------------------------------------------


class ElectoralProcess(BusinessTable, table=True):
    __tablename__ = "electoral_processes"
    __table_args__ = (
        _check_in("process_type", ProcessType, "process_type"),
        _check_in("election_level", ElectionLevel, "election_level"),
        _check_in("status", ProcessStatus, "status"),
        CheckConstraint(
            "(election_level = 'local' AND state_id IS NOT NULL) "
            "OR (election_level = 'federal' AND state_id IS NULL)",
            name="state_matches_level",
        ),
        {"schema": SCHEMA},
    )

    name: str = Field(max_length=200)
    election_year: int = Field(sa_type=SmallInteger)
    process_type: str = Field(default=ProcessType.ORDINARY, sa_type=Text)
    election_level: str = Field(sa_type=Text)
    state_id: uuid.UUID | None = _fk("states", nullable=True, schema="geography")
    framework_id: uuid.UUID = _fk("geographic_frameworks", schema="geography")
    election_date: date | None = Field(default=None, sa_type=Date)
    status: str = Field(default=ProcessStatus.DRAFT, sa_type=Text)


class ProcessOffice(BusinessTable, table=True):
    """Which offices are up for election in a process and how they are composed (D-23)."""

    __tablename__ = "process_offices"
    __table_args__ = (
        _alive_unique(
            "uq_process_offices_process_id_office_type_id", "process_id", "office_type_id"
        ),
        CheckConstraint(
            "rp_method IS NULL OR rp_method IN ('closed_list', 'best_loser', 'mixed')",
            name="rp_method",
        ),
        CheckConstraint("positions IS NULL OR positions BETWEEN 1 AND 500", name="positions"),
        {"schema": SCHEMA},
    )

    process_id: uuid.UUID = _fk("electoral_processes", ondelete="CASCADE")
    office_type_id: uuid.UUID = _fk("office_types")
    is_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    positions: int | None = Field(default=None, sa_type=SmallInteger)
    # Member of the slate headed by this office (e.g. syndic → municipal_president); NULL = own
    # nomination (D-25).
    slate_parent_office_type_id: uuid.UUID | None = _fk("office_types", nullable=True)
    rp_method: str | None = Field(default=None, sa_type=Text)
    rp_method_params: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)


class MunicipalitySetting(BusinessTable, table=True):
    __tablename__ = "municipality_settings"
    __table_args__ = (
        _alive_unique(
            "uq_municipality_settings_process_id_municipality_id", "process_id", "municipality_id"
        ),
        _check_in("election_regime", ElectionRegime, "election_regime"),
        CheckConstraint(
            "mr_councilor_count >= 0 AND rp_councilor_count >= 0 AND syndic_count >= 0",
            name="counts",
        ),
        {"schema": SCHEMA},
    )

    process_id: uuid.UUID = _fk("electoral_processes", ondelete="CASCADE")
    municipality_id: uuid.UUID = _fk("municipalities", schema="geography")
    election_regime: str = Field(default=ElectionRegime.PARTY_BASED, sa_type=Text)
    mr_councilor_count: int = Field(default=0, sa_type=SmallInteger)
    rp_councilor_count: int = Field(default=0, sa_type=SmallInteger)
    syndic_count: int = Field(default=0, sa_type=SmallInteger)


class ProcessValidationRule(BusinessTable, table=True):
    __tablename__ = "process_validation_rules"
    __table_args__ = (
        Index(
            "uq_process_validation_rules_scope",
            "process_id",
            "validation_rule_id",
            text("coalesce(office_type_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        _check_in("severity", Severity, "severity"),
        {"schema": SCHEMA},
    )

    process_id: uuid.UUID = _fk("electoral_processes", ondelete="CASCADE")
    validation_rule_id: uuid.UUID = _fk("validation_rules")
    office_type_id: uuid.UUID | None = _fk("office_types", nullable=True)
    is_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    severity: str = Field(default=Severity.BLOCKING, sa_type=Text)
    params: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)


class Coalition(BusinessTable, table=True):
    __tablename__ = "coalitions"
    __table_args__ = (
        _check_in("coalition_kind", CoalitionKind, "coalition_kind"),
        {"schema": SCHEMA},
    )

    process_id: uuid.UUID = _fk("electoral_processes", ondelete="CASCADE")
    name: str = Field(max_length=200)
    coalition_kind: str = Field(default=CoalitionKind.COALITION, sa_type=Text)


class CoalitionParty(BusinessTable, table=True):
    __tablename__ = "coalition_parties"
    __table_args__ = (
        _alive_unique("uq_coalition_parties_coalition_id_party_id", "coalition_id", "party_id"),
        {"schema": SCHEMA},
    )

    coalition_id: uuid.UUID = _fk("coalitions", ondelete="CASCADE")
    party_id: uuid.UUID = _fk("parties")


# --- nominations and formulas (D-27, D-29) ---------------------------------------------------


def _nomination_geography_check() -> CheckConstraint:
    columns = list(GEO_COLUMNS.values())
    clauses = [
        f"(geographic_level = '{level.value}' AND num_nonnulls({', '.join(columns)}) = 1 AND "
        f"{column} IS NOT NULL)"
        for level, column in GEO_COLUMNS.items()
    ]
    clauses.append(f"(geographic_level = 'national' AND num_nonnulls({', '.join(columns)}) = 0)")
    return CheckConstraint(" OR ".join(clauses), name="geography_matches_level")


class Nomination(BusinessTable, table=True):
    __tablename__ = "nominations"
    __table_args__ = (
        _nomination_geography_check(),
        CheckConstraint("num_nonnulls(party_id, coalition_id) = 1", name="one_nominator"),
        _check_in("status", NominationStatus, "status"),
        _check_in("geographic_level", GeographicLevel, "geographic_level"),
        Index(
            "uq_nominations_active",
            "process_id",
            "office_type_id",
            text(
                "coalesce(electoral_region_id, state_id, federal_district_id, local_district_id, "
                "municipality_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            text("coalesce(party_id, coalition_id)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND status <> 'cancelled'"),
        ),
        {"schema": SCHEMA},
    )

    process_id: uuid.UUID = _fk("electoral_processes")
    office_type_id: uuid.UUID = _fk("office_types")
    geographic_level: str = Field(sa_type=Text)
    electoral_region_id: uuid.UUID | None = _fk(
        "electoral_regions", nullable=True, schema="geography"
    )
    state_id: uuid.UUID | None = _fk("states", nullable=True, schema="geography")
    federal_district_id: uuid.UUID | None = _fk(
        "federal_districts", nullable=True, schema="geography"
    )
    local_district_id: uuid.UUID | None = _fk("local_districts", nullable=True, schema="geography")
    municipality_id: uuid.UUID | None = _fk("municipalities", nullable=True, schema="geography")
    party_id: uuid.UUID | None = _fk("parties", nullable=True)
    coalition_id: uuid.UUID | None = _fk("coalitions", nullable=True)
    status: str = Field(default=NominationStatus.DRAFT, sa_type=Text)
    notes: str | None = None


class Formula(BusinessTable, table=True):
    __tablename__ = "formulas"
    __table_args__ = (
        Index(
            "uq_formulas_active_position",
            "nomination_id",
            "office_type_id",
            "position",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND status NOT IN ('substituted', 'cancelled')"
            ),
        ),
        _check_in("status", FormulaStatus, "status"),
        CheckConstraint("position BETWEEN 1 AND 500", name="position"),
        {"schema": SCHEMA},
    )

    nomination_id: uuid.UUID = _fk("nominations", ondelete="CASCADE")
    office_type_id: uuid.UUID = _fk("office_types")
    position: int = Field(sa_type=SmallInteger)
    status: str = Field(default=FormulaStatus.ASPIRANT, sa_type=Text)
    origin_party_id: uuid.UUID | None = _fk("parties", nullable=True)
    replaces_formula_id: uuid.UUID | None = _fk("formulas", nullable=True, ondelete="SET NULL")
    substitution_reason: str | None = Field(default=None, max_length=500)


class FormulaMember(BusinessTable, table=True):
    __tablename__ = "formula_members"
    __table_args__ = (
        _alive_unique("uq_formula_members_formula_id_member_role", "formula_id", "member_role"),
        _check_in("member_role", MemberRole, "member_role"),
        Index("ix_formula_members_process_id_person_id", "process_id", "person_id"),
        {"schema": SCHEMA},
    )

    formula_id: uuid.UUID = _fk("formulas", ondelete="CASCADE")
    person_id: uuid.UUID = Field(foreign_key="people.persons.id", ondelete="RESTRICT")
    process_id: uuid.UUID = Field(
        foreign_key=f"{SCHEMA}.electoral_processes.id", ondelete="CASCADE"
    )
    member_role: str = Field(sa_type=Text)


class FormulaStatusHistory(BusinessTable, table=True):
    __tablename__ = "formula_status_history"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    formula_id: uuid.UUID = _fk("formulas", ondelete="CASCADE")
    from_status: str | None = Field(default=None, sa_type=Text)
    to_status: str = Field(sa_type=Text)
    reason: str | None = Field(default=None, max_length=500)
    changed_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="identity.users.id", ondelete="SET NULL"
    )
    changed_at: datetime = Field(sa_type=TZ)


class RuleOverride(BusinessTable, table=True):
    """A business-rule violation accepted on purpose, with who and why (D-28)."""

    __tablename__ = "rule_overrides"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}

    nomination_id: uuid.UUID = _fk("nominations", ondelete="CASCADE")
    formula_id: uuid.UUID | None = _fk("formulas", nullable=True, ondelete="CASCADE")
    validation_rule_id: uuid.UUID = _fk("validation_rules")
    overridden_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="identity.users.id", ondelete="SET NULL"
    )
    reason: str = Field(max_length=500)
    details: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
