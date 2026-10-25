import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.candidacies.models import (
    CoalitionKind,
    ElectionLevel,
    ElectionRegime,
    FormulaStatus,
    GeographicLevel,
    NominationKind,
    NominationStatus,
    Principle,
    ProcessStatus,
    ProcessType,
    RpMethod,
    Severity,
)

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,49}$")]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# --- catalogs --------------------------------------------------------------------------------


class PartyIn(Schema):
    acronym: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    is_own_party: bool = False
    color_hex: Annotated[str | None, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")] = None
    logo_uri: Annotated[str | None, Field(max_length=500)] = None


class PartyOut(PartyIn):
    id: uuid.UUID


class OfficeTypeIn(Schema):
    code: Code
    name: Text200
    election_level: ElectionLevel
    geographic_level: GeographicLevel
    principle: Principle
    nomination_kind: NominationKind
    default_positions: Annotated[int | None, Field(ge=1, le=500)] = None
    has_substitute: bool = True
    sort_order: int = 100


class OfficeTypeOut(OfficeTypeIn):
    id: uuid.UUID


class ValidationRuleOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str
    default_params: dict[str, Any]


# --- processes ------------------------------------------------------------------------------


class ProcessIn(Schema):
    name: Text200
    election_year: Annotated[int, Field(ge=2000, le=2100)]
    process_type: ProcessType = ProcessType.ORDINARY
    election_level: ElectionLevel
    state_id: uuid.UUID | None = Field(default=None, description="Obligatorio en procesos locales.")
    election_date: date | None = None


class ProcessUpdate(Schema):
    name: Text200 | None = None
    election_date: date | None = None
    status: ProcessStatus | None = None


class ProcessOut(Schema):
    id: uuid.UUID
    name: str
    election_year: int
    process_type: ProcessType
    election_level: ElectionLevel
    state_id: uuid.UUID | None
    framework_id: uuid.UUID
    election_date: date | None
    status: ProcessStatus


class ProcessOfficeIn(Schema):
    office_type_id: uuid.UUID
    is_enabled: bool
    positions: Annotated[int | None, Field(ge=1, le=500)] = None
    slate_parent_office_type_id: uuid.UUID | None = None
    rp_method: RpMethod | None = None
    rp_method_params: dict[str, Any] = Field(default_factory=dict)


class ProcessOfficeOut(ProcessOfficeIn):
    office_code: str
    office_name: str


class MunicipalitySettingIn(Schema):
    municipality_id: uuid.UUID
    election_regime: ElectionRegime = ElectionRegime.PARTY_BASED
    mr_councilor_count: Annotated[int, Field(ge=0, le=100)] = 0
    rp_councilor_count: Annotated[int, Field(ge=0, le=100)] = 0
    syndic_count: Annotated[int, Field(ge=0, le=10)] = 0


class MunicipalitySettingOut(MunicipalitySettingIn):
    id: uuid.UUID


class ProcessRuleIn(Schema):
    rule_code: Code
    office_type_id: uuid.UUID | None = None
    is_enabled: bool
    severity: Severity = Severity.BLOCKING
    params: dict[str, Any] = Field(default_factory=dict)


class ProcessRuleOut(ProcessRuleIn):
    id: uuid.UUID
    effective_params: dict[str, Any]


class CoalitionIn(Schema):
    name: Text200
    coalition_kind: CoalitionKind = CoalitionKind.COALITION
    party_ids: list[uuid.UUID] = Field(min_length=2, max_length=20)


class CoalitionOut(Schema):
    id: uuid.UUID
    name: str
    coalition_kind: CoalitionKind
    party_ids: list[uuid.UUID]


# --- nominations and formulas ---------------------------------------------------------------


class Override(Schema):
    rules: list[Code] = Field(
        min_length=1, max_length=10, description="Reglas que se aceptan violar."
    )
    reason: Reason


class NominationIn(Schema):
    process_id: uuid.UUID
    office_type_id: uuid.UUID
    node_id: uuid.UUID | None = Field(
        default=None,
        description="Nodo del nivel geográfico del cargo; vacío para cargos nacionales.",
    )
    party_id: uuid.UUID | None = None
    coalition_id: uuid.UUID | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None


class NominationUpdate(Schema):
    notes: Annotated[str | None, Field(max_length=2000)] = None


class FormulaIn(Schema):
    office_type_id: uuid.UUID
    position: Annotated[int, Field(ge=1, le=500)]
    owner_person_id: uuid.UUID
    substitute_person_id: uuid.UUID | None = Field(
        default=None, description="Obligatoria salvo en cargos sin suplencia."
    )
    origin_party_id: uuid.UUID | None = None
    override: Override | None = None


class FormulaMembersUpdate(Schema):
    owner_person_id: uuid.UUID | None = None
    substitute_person_id: uuid.UUID | None = None
    origin_party_id: uuid.UUID | None = None
    override: Override | None = None


class FormulaStatusIn(Schema):
    to_status: Literal["registered", "approved", "cancelled"]
    reason: Reason | None = None


class SubstitutionIn(Schema):
    owner_person_id: uuid.UUID | None = Field(
        default=None, description="Vacío: conserva a la propietaria."
    )
    substitute_person_id: uuid.UUID | None = Field(
        default=None, description="Vacío: conserva a la suplente."
    )
    reason: Reason
    override: Override | None = None


class NominationAction(Schema):
    reason: Reason | None = None
    override: Override | None = None


class ViolationOut(Schema):
    rule: str
    severity: Severity
    message: str
    formula_id: uuid.UUID | None = None


class MemberOut(Schema):
    person_id: uuid.UUID
    full_name: str
    sex: str | None


class FormulaOut(Schema):
    id: uuid.UUID
    office_type_id: uuid.UUID
    office_code: str
    position: int
    status: FormulaStatus
    origin_party_id: uuid.UUID | None
    replaces_formula_id: uuid.UUID | None
    substitution_reason: str | None
    owner: MemberOut | None
    substitute: MemberOut | None


class SlotOut(Schema):
    office_type_id: uuid.UUID
    office_code: str
    office_name: str
    expected: int
    filled: int
    missing_positions: list[int]


class NominationSummary(Schema):
    id: uuid.UUID
    process_id: uuid.UUID
    office_type_id: uuid.UUID
    office_code: str
    geographic_level: GeographicLevel
    node_id: uuid.UUID | None
    party_id: uuid.UUID | None
    coalition_id: uuid.UUID | None
    status: NominationStatus
    created_at: datetime


class NominationOut(NominationSummary):
    notes: str | None
    editable: bool = Field(
        description="False: el usuario solo puede consultarla (alcance parcial)."
    )
    complete: bool
    slots: list[SlotOut]
    formulas: list[FormulaOut]
    warnings: list[ViolationOut] = Field(default_factory=list)


class StatusHistoryOut(Schema):
    formula_id: uuid.UUID
    office_code: str
    position: int
    from_status: str | None
    to_status: str
    reason: str | None
    changed_by_user_id: uuid.UUID | None
    changed_at: datetime
