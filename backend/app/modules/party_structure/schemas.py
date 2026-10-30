"""DTOs of the party structure (API)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.identity.schemas import RoleSummary
from app.modules.party_structure.models import (
    AppointmentKind,
    CoordinationKind,
    DistrictKind,
    EndReason,
    ScopeRule,
    TerritorialLevel,
)
from app.modules.people.schemas import PersonSummary


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


Code = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
Name = Field(min_length=2, max_length=200)

# --- catalog ----------------------------------------------------------------------------------


class PositionTypeRef(Schema):
    id: uuid.UUID
    code: str
    name: str


class PositionTypeOut(Schema):
    id: uuid.UUID
    body_type_id: uuid.UUID
    code: str
    name: str
    scope_rule: ScopeRule
    electing_body: str | None
    term_years: int | None
    term_months: int | None
    max_consecutive_terms: int | None
    statutory_basis: str | None
    default_role: RoleSummary | None
    is_derived: bool
    derived_from: list[PositionTypeRef] = Field(
        description="De qué cargos toma a su titular. Uno: fijo; varios: se elige en cada periodo."
    )
    sort_order: int


class BodyTypeOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    territorial_level: TerritorialLevel
    requires_installation: bool
    statutory_basis: str | None
    description: str | None
    sort_order: int
    positions: list[PositionTypeOut]


class BodyTypeIn(Schema):
    code: str = Code
    name: str = Name
    territorial_level: TerritorialLevel
    requires_installation: bool = False
    statutory_basis: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class BodyTypeUpdate(Schema):
    name: str = Name
    statutory_basis: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class PositionTypeIn(Schema):
    body_type_id: uuid.UUID
    code: str = Code
    name: str = Name
    scope_rule: ScopeRule = ScopeRule.BODY_TERRITORY
    electing_body: str | None = Field(default=None, max_length=300)
    term_years: int | None = Field(default=None, ge=1, le=20)
    term_months: int | None = Field(default=None, ge=1, le=240)
    max_consecutive_terms: int | None = Field(default=None, ge=1, le=20)
    statutory_basis: str | None = Field(default=None, max_length=300)
    default_role_id: uuid.UUID | None = None
    derived_from: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=10,
        description="Cargos de los que toma a su titular (Presídium). Vacío: se nombra.",
    )
    sort_order: int = 0


class PositionTypeUpdate(Schema):
    name: str = Name
    electing_body: str | None = Field(default=None, max_length=300)
    term_years: int | None = Field(default=None, ge=1, le=20)
    term_months: int | None = Field(default=None, ge=1, le=240)
    max_consecutive_terms: int | None = Field(default=None, ge=1, le=20)
    statutory_basis: str | None = Field(default=None, max_length=300)
    default_role_id: uuid.UUID | None = None
    sort_order: int = 0


class IncompatibilityIn(Schema):
    position_type_a_id: uuid.UUID
    position_type_b_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=500)


class IncompatibilityOut(Schema):
    id: uuid.UUID
    position_type_a: PositionTypeRef
    position_type_b: PositionTypeRef
    notes: str | None


class CoordinationPositionTypeIn(Schema):
    kind: CoordinationKind
    code: str = Code
    name: str = Name
    default_role_id: uuid.UUID | None = None
    sort_order: int = 0


class CoordinationPositionTypeOut(Schema):
    id: uuid.UUID
    kind: CoordinationKind
    code: str
    name: str
    default_role: RoleSummary | None
    sort_order: int


# --- bodies -----------------------------------------------------------------------------------


class BodyTypeRef(Schema):
    id: uuid.UUID
    code: str
    name: str
    territorial_level: TerritorialLevel


class BodyOut(Schema):
    id: uuid.UUID
    body_type: BodyTypeRef
    state_code: int | None
    territory: str = Field(description="Nombre del territorio en el marco activo.")
    framework_id: uuid.UUID | None
    municipality_id: uuid.UUID | None
    federal_district_id: uuid.UUID | None
    local_district_id: uuid.UUID | None
    district_kind: DistrictKind | None
    installed_on: date | None
    installation_agreement: str | None
    dissolved_on: date | None
    dissolution_agreement: str | None
    status: Literal["installed", "dissolved"]


class BodyInstallIn(Schema):
    """Registers the installation of a district or municipal body (agreement of the CDN)."""

    body_type_id: uuid.UUID
    municipality_id: uuid.UUID | None = None
    federal_district_id: uuid.UUID | None = None
    local_district_id: uuid.UUID | None = None
    installed_on: date
    installation_agreement: str = Field(min_length=2, max_length=300)


class BodyDissolveIn(Schema):
    dissolved_on: date
    dissolution_agreement: str = Field(min_length=2, max_length=300)


# --- seats and appointments (phase 2) ---------------------------------------------------------


class AccessIn(Schema):
    """Access to the system for the holder (D-104). The account is the person's: it is reused if
    it exists; if not, `email` is required and an invitation is sent."""

    email: EmailStr | None = None
    role_id: uuid.UUID | None = Field(
        default=None, description="Vacío: el rol por defecto del cargo."
    )


class AppointmentIn(Schema):
    person_id: uuid.UUID = Field(description="Persona registrada con CURP.")
    kind: AppointmentKind
    starts_on: date
    ends_on: date | None = Field(
        default=None, description="Vacío: se propone con el periodo del cargo."
    )
    appointed_by: str | None = Field(default=None, max_length=300)
    agreement_ref: str | None = Field(default=None, max_length=300)
    access: AccessIn | None = Field(
        default=None,
        description=(
            "Dar acceso al sistema. Si quien nombra no puede darlo, el nombramiento se registra "
            "sin acceso y `access_pending` dice por qué (D-104)."
        ),
    )


class AppointmentUpdate(Schema):
    ends_on: date | None = None
    appointed_by: str | None = Field(default=None, max_length=300)
    agreement_ref: str | None = Field(default=None, max_length=300)


class AppointmentEndIn(Schema):
    ended_on: date
    reason: EndReason
    notes: str | None = Field(default=None, max_length=500)


class AppointmentOut(Schema):
    id: uuid.UUID
    position_id: uuid.UUID
    person: PersonSummary
    kind: AppointmentKind
    appointed_by: str | None
    agreement_ref: str | None
    starts_on: date
    ends_on: date | None
    ended_on: date | None
    end_reason: EndReason | None
    end_notes: str | None
    role: RoleSummary | None
    current: bool
    has_access: bool
    user_id: uuid.UUID | None = Field(description="Cuenta de la persona, si el cargo da acceso.")
    access_pending: str | None = Field(
        default=None, description="Por qué no se dio el acceso pedido al nombrar."
    )


class PersonAppointmentOut(AppointmentOut):
    position_type: PositionTypeRef
    body: BodyTypeRef
    body_id: uuid.UUID
    territory: str


class SeatOut(Schema):
    id: uuid.UUID
    body_id: uuid.UUID
    position_type: PositionTypeRef
    region_number: int | None = Field(
        description="Circunscripción, en las Secretarías de Circunscripción."
    )
    is_derived: bool
    vacant_since: date | None
    current: AppointmentOut | None
    derived_from: PositionTypeRef | None = Field(
        description="En un cargo derivado, de qué cargo toma hoy a su titular."
    )
    derived_holder: PersonSummary | None
    choice_pending: bool = Field(
        description="Cargo derivado con varias opciones sin elegir para el periodo vigente."
    )


class DerivedChoiceIn(Schema):
    source_position_type_id: uuid.UUID
    starts_on: date
    agreement_ref: str | None = Field(default=None, max_length=300)
