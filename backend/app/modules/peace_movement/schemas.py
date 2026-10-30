import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.people.schemas import PersonCreate, PersonOut, PersonSummary

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# --- catalogs ---------------------------------------------------------------------------------


class LevelOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    rank: int
    sort_order: int


class LevelGoalIn(Schema):
    level_id: uuid.UUID
    state_id: uuid.UUID | None = Field(default=None, description="Nulo = meta nacional.")
    recruit_goal: Annotated[int, Field(ge=0, le=1_000_000)]
    house_goal: Annotated[int | None, Field(ge=0, le=10_000)] = None
    valid_from: date | None = Field(default=None, description="Por defecto, hoy.")


class LevelGoalOut(Schema):
    id: uuid.UUID
    level_id: uuid.UUID
    state_id: uuid.UUID | None
    recruit_goal: int
    house_goal: int | None
    valid_from: date
    valid_to: date | None


class HouseGoalIn(Schema):
    state_id: uuid.UUID | None = Field(default=None, description="Nulo = meta nacional.")
    member_goal: Annotated[int, Field(ge=1, le=100_000)]
    valid_from: date | None = None


class HouseGoalOut(Schema):
    id: uuid.UUID
    state_id: uuid.UUID | None
    member_goal: int
    valid_from: date
    valid_to: date | None


class SettingsIn(Schema):
    traffic_light_yellow_pct: Annotated[int, Field(ge=1, le=999)]
    traffic_light_green_pct: Annotated[int, Field(ge=1, le=1000)]
    depth_alert_threshold: Annotated[int, Field(ge=1, le=10_000)]

    @model_validator(mode="after")
    def _ordered(self) -> "SettingsIn":
        if self.traffic_light_yellow_pct >= self.traffic_light_green_pct:
            raise ValueError("El umbral amarillo debe ser menor que el verde.")
        return self


class SettingsOut(SettingsIn):
    pass


ZoneLevelName = Literal["state", "federal_district", "local_district", "municipality", "section"]


class ZoneNodeIn(Schema):
    level: ZoneLevelName
    node_id: uuid.UUID


class ZoneNodeOut(ZoneNodeIn):
    pass


class ZoneCoordinatorIn(Schema):
    user_id: uuid.UUID
    state_id: uuid.UUID
    nodes: list[ZoneNodeIn] = Field(min_length=1, max_length=500)
    valid_from: date | None = None


class ZoneCoordinatorOut(Schema):
    id: uuid.UUID
    user_id: uuid.UUID
    state_id: uuid.UUID
    valid_from: date
    valid_to: date | None
    nodes: list[ZoneNodeOut]
    section_count: int


# --- members ----------------------------------------------------------------------------------


class ConsentCapture(Schema):
    """Acceptance of the current Peace Movement notice (D-82); the notice text comes from the
    catalog, so only how it was captured travels here."""

    channel: Literal["panel", "paper"] = "panel"
    evidence_uri: Annotated[str | None, Field(max_length=500)] = None


class EnrollmentIn(Schema):
    person_id: uuid.UUID | None = Field(
        default=None, description="Persona existente; excluyente con `person`."
    )
    person: PersonCreate | None = Field(
        default=None,
        description="Persona nueva. Si la CURP ya existe, se reutiliza esa persona sin cambiar "
        "sus datos.",
    )
    level_id: uuid.UUID
    recruiter_member_id: uuid.UUID | None = None
    origin: Literal["recruiter", "structure", "event", "campaign"] = "recruiter"
    origin_detail: Annotated[str | None, Field(max_length=300)] = None
    consent: ConsentCapture
    house_id: uuid.UUID | None = Field(
        default=None, description="Casa de Paz que integra al inscribirse."
    )

    @model_validator(mode="after")
    def _one_person(self) -> "EnrollmentIn":
        if (self.person_id is None) == (self.person is None):
            raise ValueError("Indica `person_id` o `person`, uno de los dos.")
        if (self.origin == "recruiter") != (self.recruiter_member_id is not None):
            raise ValueError(
                "Con origen «recruiter» el reclutador es obligatorio; con otro origen no lleva."
            )
        return self


class MemberSummary(Schema):
    id: uuid.UUID
    person: PersonSummary
    level_id: uuid.UUID
    status: str
    depth: int
    state_id: uuid.UUID
    section_id: uuid.UUID
    recruited_by_member_id: uuid.UUID | None
    enrolled_on: date


class DirectCounts(Schema):
    active: int
    pending: int
    total: int
    hidden: int = Field(description="Reclutas directos fuera del alcance del usuario.")


class NetworkOut(Schema):
    """Precomputed counters of the network (they reflect changes within minutes)."""

    direct_active: int
    direct_pending: int
    network_total: int = Field(description="Pacificadores activos en toda la red, sin él.")
    network_by_level: dict[str, int]
    houses_open: int
    houses_consolidated: int
    computed_at: datetime


class MemberOut(Schema):
    id: uuid.UUID
    person: PersonOut
    level_id: uuid.UUID
    status: str
    status_reason: str | None
    origin: str
    origin_detail: str | None
    channel: str
    enrolled_on: date
    left_on: date | None
    recruited_by: MemberSummary | None
    referral_code: str
    depth: int
    state_id: uuid.UUID
    section_id: uuid.UUID
    validated_at: datetime | None
    direct: DirectCounts
    recruit_goal: int | None = Field(description="Meta vigente del nivel en su estado.")
    progress_pct: int | None
    traffic_light: Literal["red", "yellow", "green"] | None
    network: NetworkOut | None = Field(description="Nulo hasta el primer cálculo de agregados.")
    house_goal: int | None = Field(description="Casas consolidadas que pide su nivel.")
    houses_progress_pct: int | None


class ReasonIn(Schema):
    reason: Reason


class LevelChangeIn(Schema):
    level_id: uuid.UUID
    reason: Reason | None = None


class ReassignIn(Schema):
    recruiter_member_id: uuid.UUID
    reason: Reason


class ChildrenPage(Schema):
    items: list[MemberSummary]
    next_cursor: str | None
    has_more: bool
    hidden: int = Field(description="Reclutas directos fuera del alcance: solo el total.")


class LevelChangeOut(Schema):
    id: uuid.UUID
    from_level_id: uuid.UUID
    to_level_id: uuid.UUID
    changed_by_user_id: uuid.UUID | None
    changed_at: datetime
    reason: str | None


class RecruiterChangeOut(Schema):
    id: uuid.UUID
    from_member_id: uuid.UUID | None
    to_member_id: uuid.UUID
    changed_by_user_id: uuid.UUID | None
    changed_at: datetime
    reason: str
    subtree_size: int


class MemberHistory(Schema):
    levels: list[LevelChangeOut]
    recruiters: list[RecruiterChangeOut]


class BranchesIn(Schema):
    member_ids: list[uuid.UUID] = Field(max_length=100)


class BranchOut(Schema):
    member_id: uuid.UUID
    person: PersonSummary
    depth: int


# --- Peace Houses -----------------------------------------------------------------------------

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class ScheduleSlot(Schema):
    day: Weekday
    starts_at: ClockTime
    ends_at: ClockTime

    @model_validator(mode="after")
    def _ordered(self) -> "ScheduleSlot":
        if self.starts_at >= self.ends_at:
            raise ValueError("La hora de inicio debe ser anterior a la de fin.")
        return self


class HouseAddressIn(Schema):
    street: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    exterior_number: Annotated[str | None, Field(max_length=30)] = None
    interior_number: Annotated[str | None, Field(max_length=30)] = None
    references: Annotated[str | None, Field(max_length=300)] = None
    postal_code: Annotated[str | None, StringConstraints(pattern=r"^\d{5}$")] = None
    # Exact point; the house's section comes from it (it must fall in the active framework).
    longitude: Annotated[float, Field(ge=-180, le=180)]
    latitude: Annotated[float, Field(ge=-90, le=90)]


class HouseIn(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
    schedule: list[ScheduleSlot] = Field(default_factory=list, max_length=21)
    capacity: Annotated[int | None, Field(ge=1, le=10_000)] = None
    address: HouseAddressIn
    opened_by_member_id: uuid.UUID
    host_member_id: uuid.UUID
    contact_member_id: uuid.UUID
    member_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=500,
        description="Integrantes además del anfitrión y el contacto, que se agregan solos.",
    )


class HouseUpdate(Schema):
    name: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)
    ] = None
    schedule: list[ScheduleSlot] | None = Field(default=None, max_length=21)
    capacity: Annotated[int | None, Field(ge=1, le=10_000)] = None
    host_member_id: uuid.UUID | None = None
    contact_member_id: uuid.UUID | None = None


class HouseAddressOut(Schema):
    street: str | None = None
    exterior_number: str | None = None
    interior_number: str | None = None
    references: str | None = None
    postal_code: str | None = None
    longitude: float | None = Field(default=None, description="Exacta; solo con permiso.")
    latitude: float | None = None


class HouseSummary(Schema):
    id: uuid.UUID
    name: str
    status: str
    state_id: uuid.UUID
    municipality_id: uuid.UUID
    section_id: uuid.UUID
    approx_longitude: float
    approx_latitude: float
    member_count: int
    credited_member_id: uuid.UUID | None
    credited_user_id: uuid.UUID | None
    credit_pending: bool
    needs_reassignment: bool
    publishable: bool
    opened_on: date


class HouseOut(HouseSummary):
    schedule: list[ScheduleSlot]
    capacity: int | None
    address: HouseAddressOut = Field(description="Calle y coordenadas exactas solo con permiso.")
    host: MemberSummary | None
    contact: MemberSummary | None
    opened_by_member_id: uuid.UUID
    member_goal: int | None
    progress_pct: int | None
    consolidated_on: date | None
    first_consolidated_on: date | None
    closed_on: date | None
    status_reason: str | None


class HouseMemberIn(Schema):
    member_id: uuid.UUID


class HouseMemberOut(Schema):
    member: MemberSummary
    joined_on: date
    source: str


class CreditIn(Schema):
    member_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    reason: Reason

    @model_validator(mode="after")
    def _one(self) -> "CreditIn":
        if (self.member_id is None) == (self.user_id is None):
            raise ValueError("Indica un pacificador o un usuario, uno de los dos.")
        return self


class GuestIn(Schema):
    given_names: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    paternal_surname: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    maternal_surname: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ] = None
    mobile: Annotated[str | None, StringConstraints(min_length=10, max_length=20)] = None


class MeetingIn(Schema):
    held_at: datetime
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
    notes: Annotated[str | None, Field(max_length=5000)] = None
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    guest_person_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=500, description="Invitados ya registrados."
    )
    guests: list[GuestIn] = Field(default_factory=list, max_length=500)


class AttendeeOut(Schema):
    person: PersonSummary
    member_id: uuid.UUID | None = Field(description="Nulo para invitados.")


class MeetingSummary(Schema):
    id: uuid.UUID
    held_at: datetime
    topic: str
    attendee_count: int
    guest_count: int


class MeetingOut(MeetingSummary):
    notes: str | None
    attendees: list[AttendeeOut]


class PhotoOut(Schema):
    id: uuid.UUID
    caption: str | None
    content_type: str
    size_bytes: int
    url: str = Field(description="URL firmada, válida unos minutos.")
    created_at: datetime


class LocationConsentIn(Schema):
    channel: Literal["panel", "paper"] = "paper"
    evidence_uri: Annotated[str | None, Field(max_length=500)] = None


# --- statistics -------------------------------------------------------------------------------


class NetworkNode(Schema):
    member: MemberSummary
    network: NetworkOut | None


class NetworkPage(Schema):
    root: NetworkNode
    items: list[NetworkNode]
    next_cursor: str | None
    has_more: bool
    hidden: int = Field(description="Integrantes de esos niveles fuera del alcance (solo total).")


class GeoStatOut(Schema):
    node_id: uuid.UUID
    label: str
    active: int
    by_level: dict[str, int]


class GrowthPoint(Schema):
    day: date
    enrollments: int
