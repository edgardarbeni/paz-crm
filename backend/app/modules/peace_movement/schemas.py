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
