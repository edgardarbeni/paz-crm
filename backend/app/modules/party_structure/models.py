"""Party structure (schema `party_structure`): the statutory catalog of bodies and positions,
and the bodies installed in each territory. See docs/modules/party-structure.md and D-101..D-108.

Territory of a body (D-107):
- national bodies have none;
- state bodies keep the INE state code (1-32), stable across geographic frameworks;
- district and municipal bodies point to a node of the framework they were installed in.
"""

import uuid
from datetime import date
from enum import StrEnum
from typing import Literal

from sqlalchemy import CheckConstraint, Date, Index, SmallInteger, Text, text
from sqlmodel import Field

from app.core.db.base import BusinessTable

SCHEMA = "party_structure"
OnDelete = Literal["CASCADE", "SET NULL", "RESTRICT"]


class TerritorialLevel(StrEnum):
    NATIONAL = "national"
    STATE = "state"
    DISTRICT = "district"
    MUNICIPAL = "municipal"


class ScopeRule(StrEnum):
    BODY_TERRITORY = "body_territory"
    CIRCUMSCRIPTION = "circumscription"
    NATIONAL = "national"


class DistrictKind(StrEnum):
    FEDERAL = "federal"
    LOCAL = "local"


class AppointmentKind(StrEnum):
    ELECTED = "elected"
    DESIGNATED = "designated"
    ACTING = "acting"  # encargado de despacho
    DELEGATE = "delegate"  # Delegación Estatal en funciones de Presidencia (D-107)


class EndReason(StrEnum):
    TERM_END = "term_end"
    RESIGNATION = "resignation"
    REMOVAL = "removal"
    DEATH = "death"
    OTHER = "other"


class CoordinationKind(StrEnum):
    FEDERAL = "federal"
    LOCAL = "local"
    SECTIONAL = "sectional"


def _in(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN ({', '.join(repr(v.value) for v in values)})", name=name)


def _fk(target: str, *, nullable: bool = False, ondelete: OnDelete = "RESTRICT") -> object:
    if nullable:
        return Field(default=None, foreign_key=target, ondelete=ondelete, nullable=True, index=True)
    return Field(foreign_key=target, ondelete=ondelete, index=True)


# --- catalog ----------------------------------------------------------------------------------


class BodyType(BusinessTable, table=True):
    """A kind of body from the statute (e.g. «Comité Directivo Estatal»)."""

    __tablename__ = "body_types"
    __table_args__ = (
        _in("territorial_level", TerritorialLevel, "territorial_level"),
        Index(
            "uq_body_types_code", "code", unique=True, postgresql_where=text("deleted_at IS NULL")
        ),
        {"schema": SCHEMA},
    )

    code: str = Field(max_length=80)
    name: str = Field(max_length=200)
    territorial_level: TerritorialLevel = Field(sa_type=Text)
    # District and municipal bodies exist only once their installation is registered.
    requires_installation: bool = False
    statutory_basis: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class PositionType(BusinessTable, table=True):
    """A position of a body type (e.g. «Dirección Jurídica Estatal»)."""

    __tablename__ = "position_types"
    __table_args__ = (
        _in("scope_rule", ScopeRule, "scope_rule"),
        Index(
            "uq_position_types_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("term_years IS NULL OR term_years > 0", name="term_years"),
        CheckConstraint("term_months IS NULL OR term_months > 0", name="term_months"),
        CheckConstraint(
            "max_consecutive_terms IS NULL OR max_consecutive_terms > 0",
            name="max_consecutive_terms",
        ),
        {"schema": SCHEMA},
    )

    body_type_id: uuid.UUID = _fk(f"{SCHEMA}.body_types.id")  # type: ignore[assignment]
    code: str = Field(max_length=80)
    name: str = Field(max_length=200)
    scope_rule: ScopeRule = Field(default=ScopeRule.BODY_TERRITORY, sa_type=Text)
    # One seat per body, or one per circumscription of the active framework.
    electing_body: str | None = Field(default=None, max_length=300)
    term_years: int | None = Field(default=None, sa_type=SmallInteger)
    term_months: int | None = Field(default=None, sa_type=SmallInteger)
    max_consecutive_terms: int | None = Field(default=None, sa_type=SmallInteger)
    statutory_basis: str | None = Field(default=None, max_length=300)
    default_role_id: uuid.UUID | None = _fk("identity.roles.id", nullable=True, ondelete="SET NULL")  # type: ignore[assignment]
    # Derived positions (Presídium) take the holder of another position; see derivations.
    is_derived: bool = False
    # Proposed length of a `delegate` appointment; NULL = the position takes no delegates.
    delegate_months: int | None = Field(default=None, sa_type=SmallInteger)
    sort_order: int = 0


class PositionDerivation(BusinessTable, table=True):
    """Where a derived position takes its holder from. One source: fixed; several: chosen in
    each period among them (Vicepresidencia del Presídium nacional, D-105)."""

    __tablename__ = "position_derivations"
    __table_args__ = (
        Index(
            "uq_position_derivations_pair",
            "position_type_id",
            "source_position_type_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    position_type_id: uuid.UUID = _fk(f"{SCHEMA}.position_types.id")  # type: ignore[assignment]
    source_position_type_id: uuid.UUID = _fk(f"{SCHEMA}.position_types.id")  # type: ignore[assignment]


class PositionIncompatibility(BusinessTable, table=True):
    """Pairs a person cannot hold at the same time (stored with a < b)."""

    __tablename__ = "position_incompatibilities"
    __table_args__ = (
        CheckConstraint("position_type_a_id < position_type_b_id", name="ordered_pair"),
        Index(
            "uq_position_incompatibilities_pair",
            "position_type_a_id",
            "position_type_b_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    position_type_a_id: uuid.UUID = _fk(f"{SCHEMA}.position_types.id")  # type: ignore[assignment]
    position_type_b_id: uuid.UUID = _fk(f"{SCHEMA}.position_types.id")  # type: ignore[assignment]
    notes: str | None = Field(default=None, max_length=500)


class CoordinationPositionType(BusinessTable, table=True):
    """Positions of a territorial coordination's team: always the coordinator, plus others."""

    __tablename__ = "coordination_position_types"
    __table_args__ = (
        _in("kind", CoordinationKind, "kind"),
        Index(
            "uq_coordination_position_types_kind_code",
            "kind",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    kind: CoordinationKind = Field(sa_type=Text)
    code: str = Field(max_length=80)
    name: str = Field(max_length=200)
    default_role_id: uuid.UUID | None = _fk("identity.roles.id", nullable=True, ondelete="SET NULL")  # type: ignore[assignment]
    sort_order: int = 0


# --- installed bodies -------------------------------------------------------------------------


class Body(BusinessTable, table=True):
    """A body in a territory. National and state bodies are seeded installed; district and
    municipal ones exist only from their installation (D-107)."""

    __tablename__ = "bodies"
    __table_args__ = (
        _in("district_kind", DistrictKind, "district_kind"),
        CheckConstraint("state_code IS NULL OR state_code BETWEEN 1 AND 32", name="state_code"),
        CheckConstraint(
            "num_nonnulls(municipality_id, federal_district_id, local_district_id) <= 1",
            name="one_node",
        ),
        CheckConstraint(
            "(municipality_id IS NULL AND federal_district_id IS NULL "
            "AND local_district_id IS NULL) = (framework_id IS NULL)",
            name="node_has_framework",
        ),
        CheckConstraint(
            "dissolved_on IS NULL OR installed_on IS NULL OR dissolved_on >= installed_on",
            name="dates",
        ),
        # One current body of each type per territory.
        Index(
            "uq_bodies_current",
            "body_type_id",
            text("coalesce(state_code, 0)"),
            text(
                "coalesce(municipality_id, federal_district_id, local_district_id, "
                "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            unique=True,
            postgresql_where=text("dissolved_on IS NULL AND deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    body_type_id: uuid.UUID = _fk(f"{SCHEMA}.body_types.id")  # type: ignore[assignment]
    state_code: int | None = Field(default=None, sa_type=SmallInteger, index=True)
    framework_id: uuid.UUID | None = _fk(  # type: ignore[assignment]
        "geography.geographic_frameworks.id", nullable=True
    )
    municipality_id: uuid.UUID | None = _fk("geography.municipalities.id", nullable=True)  # type: ignore[assignment]
    federal_district_id: uuid.UUID | None = _fk("geography.federal_districts.id", nullable=True)  # type: ignore[assignment]
    local_district_id: uuid.UUID | None = _fk("geography.local_districts.id", nullable=True)  # type: ignore[assignment]
    district_kind: DistrictKind | None = Field(default=None, sa_type=Text)
    installed_on: date | None = Field(default=None, sa_type=Date)
    installation_agreement: str | None = Field(default=None, max_length=300)
    dissolved_on: date | None = Field(default=None, sa_type=Date)
    dissolution_agreement: str | None = Field(default=None, max_length=300)


# --- seats and appointments (phase 2, D-108) --------------------------------------------------


class Position(BusinessTable, table=True):
    """A seat that is held: a position type in a body. Circumscription positions have one seat
    per circumscription (`region_number`, stable across frameworks like the state code)."""

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("region_number IS NULL OR region_number > 0", name="region_number"),
        Index(
            "uq_positions_seat",
            "body_id",
            "position_type_id",
            text("coalesce(region_number, 0)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    body_id: uuid.UUID = _fk(f"{SCHEMA}.bodies.id")  # type: ignore[assignment]
    position_type_id: uuid.UUID = _fk(f"{SCHEMA}.position_types.id")  # type: ignore[assignment]
    region_number: int | None = Field(default=None, sa_type=SmallInteger)
    vacant_since: date | None = Field(default=None, sa_type=Date)


class Appointment(BusinessTable, table=True):
    """Who holds a seat and for which period. Never deleted: ending it keeps the history."""

    __tablename__ = "appointments"
    __table_args__ = (
        _in("kind", AppointmentKind, "kind"),
        _in("end_reason", EndReason, "end_reason"),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="period"),
        CheckConstraint("ended_on IS NULL OR ended_on >= starts_on", name="ended"),
        CheckConstraint("(ended_on IS NULL) = (end_reason IS NULL)", name="end_reason_set"),
        # At most one current appointment per seat.
        Index(
            "uq_appointments_current",
            "position_id",
            unique=True,
            postgresql_where=text("ended_on IS NULL AND deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    position_id: uuid.UUID = _fk(f"{SCHEMA}.positions.id")  # type: ignore[assignment]
    person_id: uuid.UUID = _fk("people.persons.id")  # type: ignore[assignment]
    kind: AppointmentKind = Field(sa_type=Text)
    appointed_by: str | None = Field(default=None, max_length=300)
    agreement_ref: str | None = Field(default=None, max_length=300)
    starts_on: date = Field(sa_type=Date)
    ends_on: date | None = Field(default=None, sa_type=Date)
    ended_on: date | None = Field(default=None, sa_type=Date)
    end_reason: EndReason | None = Field(default=None, sa_type=Text)
    end_notes: str | None = Field(default=None, max_length=500)
    # Access to the system (phase 3, D-104): decided per appointment.
    grants_access: bool = False
    role_id: uuid.UUID | None = _fk("identity.roles.id", nullable=True, ondelete="SET NULL")  # type: ignore[assignment]


class DerivedChoice(BusinessTable, table=True):
    """For a derived seat with several possible sources, which one holds it in each period
    (Vicepresidencia del Presídium nacional, D-105)."""

    __tablename__ = "derived_choices"
    __table_args__ = (
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="period"),
        Index(
            "uq_derived_choices_current",
            "position_id",
            unique=True,
            postgresql_where=text("ends_on IS NULL AND deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    position_id: uuid.UUID = _fk(f"{SCHEMA}.positions.id")  # type: ignore[assignment]
    source_position_type_id: uuid.UUID = _fk(f"{SCHEMA}.position_types.id")  # type: ignore[assignment]
    starts_on: date = Field(sa_type=Date)
    ends_on: date | None = Field(default=None, sa_type=Date)
    agreement_ref: str | None = Field(default=None, max_length=300)
