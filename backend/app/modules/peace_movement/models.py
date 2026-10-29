"""Peace Movement (schema `peace_movement`): the recruitment pyramid, its goals and zone
coordinators. See docs/modules/peace-movement.md and D-82..D-92.

The pyramid is a materialized `ltree` path of internal bigint labels (`tree_id`), so subtree and
ancestor reads use the GiST index and never recurse (D-91).
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType
from sqlmodel import Field, SQLModel

from app.core.db.base import BusinessTable

SCHEMA = "peace_movement"
TZ = DateTime(timezone=True)
OnDelete = Literal["CASCADE", "SET NULL", "RESTRICT"]


class Ltree(UserDefinedType[str]):
    """PostgreSQL `ltree` (extension), exchanged as text."""

    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "ltree"


# Reflection (Alembic autogenerate) recognizes the column type instead of warning.
ischema_names["ltree"] = Ltree


class MemberStatus(StrEnum):
    PENDING_VALIDATION = "pending_validation"
    ACTIVE = "active"
    REJECTED = "rejected"
    LEFT = "left"  # left the movement; the person stays in `people`
    WITHDRAWN = "withdrawn"  # ARCO cancellation of the person (D-69)


class MemberOrigin(StrEnum):
    RECRUITER = "recruiter"
    STRUCTURE = "structure"
    EVENT = "event"
    CAMPAIGN = "campaign"


class EnrollmentChannel(StrEnum):
    PANEL = "panel"
    REFERRAL_LINK = "referral_link"
    IMPORT = "import"
    FIELD_APP = "field_app"


# Statuses that occupy the person's single "current" membership.
CURRENT_STATUSES = (MemberStatus.PENDING_VALIDATION, MemberStatus.ACTIVE)


def _in(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN ({', '.join(repr(v.value) for v in values)})", name=name)


def _fk(target: str, *, nullable: bool = False, ondelete: OnDelete = "RESTRICT") -> Any:
    if nullable:
        return Field(default=None, foreign_key=target, ondelete=ondelete, nullable=True, index=True)
    return Field(foreign_key=target, ondelete=ondelete, index=True)


# --- catalogs and configuration ---------------------------------------------------------------


class ParticipationLevel(BusinessTable, table=True):
    __tablename__ = "participation_levels"
    __table_args__ = ({"schema": SCHEMA},)

    code: str = Field(max_length=50, unique=True)
    name: str = Field(max_length=100)
    rank: int = Field(sa_type=SmallInteger, unique=True)
    sort_order: int = Field(sa_type=SmallInteger)


class LevelGoal(BusinessTable, table=True):
    """Recruitment (and house) goal of a level, per state or national (`state_id` null). One
    current row per level and state (`valid_to` null); changing a goal closes it (D-92)."""

    __tablename__ = "level_goals"
    __table_args__ = (
        Index(
            "uq_level_goals_current",
            "level_id",
            text("coalesce(state_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("valid_to IS NULL AND deleted_at IS NULL"),
        ),
        CheckConstraint("recruit_goal >= 0", name="recruit_goal"),
        CheckConstraint("house_goal IS NULL OR house_goal >= 0", name="house_goal"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="validity"),
        {"schema": SCHEMA},
    )

    level_id: uuid.UUID = _fk(f"{SCHEMA}.participation_levels.id")
    state_id: uuid.UUID | None = _fk("geography.states.id", nullable=True)
    recruit_goal: int
    house_goal: int | None = None
    valid_from: date = Field(sa_type=Date)
    valid_to: date | None = Field(default=None, sa_type=Date)


class HouseGoal(BusinessTable, table=True):
    """Members a Peace House needs to be consolidated, per state or national (`state_id` null)."""

    __tablename__ = "house_goals"
    __table_args__ = (
        Index(
            "uq_house_goals_current",
            text("coalesce(state_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("valid_to IS NULL AND deleted_at IS NULL"),
        ),
        CheckConstraint("member_goal > 0", name="member_goal"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="validity"),
        {"schema": SCHEMA},
    )

    state_id: uuid.UUID | None = _fk("geography.states.id", nullable=True)
    member_goal: int
    valid_from: date = Field(sa_type=Date)
    valid_to: date | None = Field(default=None, sa_type=Date)


class Settings(BusinessTable, table=True):
    """Module configuration editable by admins (D-92). A single row."""

    __tablename__ = "settings"
    __table_args__ = (
        Index("uq_settings_singleton", text("(true)"), unique=True),
        CheckConstraint(
            "0 < traffic_light_yellow_pct AND traffic_light_yellow_pct < traffic_light_green_pct",
            name="traffic_light",
        ),
        CheckConstraint("depth_alert_threshold > 0", name="depth_alert_threshold"),
        {"schema": SCHEMA},
    )

    traffic_light_yellow_pct: int = Field(default=50, sa_type=SmallInteger)
    traffic_light_green_pct: int = Field(default=100, sa_type=SmallInteger)
    depth_alert_threshold: int = Field(default=50)


class ZoneCoordinator(BusinessTable, table=True):
    """A system user who receives the credit of Peace Houses with no Ambassador above them, in
    a zone of a state (D-92). Several per state; validity keeps the history."""

    __tablename__ = "zone_coordinators"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="validity"),
        {"schema": SCHEMA},
    )

    user_id: uuid.UUID = _fk("identity.users.id")
    state_id: uuid.UUID = _fk("geography.states.id")
    valid_from: date = Field(sa_type=Date)
    valid_to: date | None = Field(default=None, sa_type=Date)


class ZoneLevel(StrEnum):
    STATE = "state"
    FEDERAL_DISTRICT = "federal_district"
    LOCAL_DISTRICT = "local_district"
    MUNICIPALITY = "municipality"
    SECTION = "section"


ZONE_LEVELS: dict[str, str] = {level.value: f"{level.value}_id" for level in ZoneLevel}


def _zone_check() -> CheckConstraint:
    columns = ", ".join(ZONE_LEVELS.values())
    clauses = [
        f"(level = '{level}' AND num_nonnulls({columns}) = 1 AND {column} IS NOT NULL)"
        for level, column in ZONE_LEVELS.items()
    ]
    return CheckConstraint(" OR ".join(clauses), name="level_matches_node")


class ZoneCoordinatorNode(BusinessTable, table=True):
    """A node of any level that forms part of a coordinator's zone (one FK column per level)."""

    __tablename__ = "zone_coordinator_nodes"
    __table_args__ = (
        _in("level", ZoneLevel, "level"),
        _zone_check(),
        {"schema": SCHEMA},
    )

    zone_coordinator_id: uuid.UUID = _fk(f"{SCHEMA}.zone_coordinators.id", ondelete="CASCADE")
    level: str = Field(sa_type=Text)
    state_id: uuid.UUID | None = _fk("geography.states.id", nullable=True)
    federal_district_id: uuid.UUID | None = _fk("geography.federal_districts.id", nullable=True)
    local_district_id: uuid.UUID | None = _fk("geography.local_districts.id", nullable=True)
    municipality_id: uuid.UUID | None = _fk("geography.municipalities.id", nullable=True)
    section_id: uuid.UUID | None = _fk("geography.sections.id", nullable=True)


class ZoneCoordinatorSection(SQLModel, table=True):
    """Derived: the sections a coordinator's zone resolves to (like `user_scope_sections`)."""

    __tablename__ = "zone_coordinator_sections"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": SCHEMA}
    __audit__: ClassVar[bool] = False

    zone_coordinator_id: uuid.UUID = Field(
        foreign_key=f"{SCHEMA}.zone_coordinators.id", ondelete="CASCADE", primary_key=True
    )
    section_id: uuid.UUID = Field(
        foreign_key="geography.sections.id", ondelete="CASCADE", primary_key=True, index=True
    )


# --- members ----------------------------------------------------------------------------------


class Member(BusinessTable, table=True):
    """A person's membership in the Peace Movement (a node of the pyramid)."""

    __tablename__ = "members"
    __table_args__ = (
        Index(
            "uq_members_current_person",
            "person_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending_validation', 'active') AND deleted_at IS NULL"
            ),
        ),
        Index("ix_members_path", "path", postgresql_using="gist"),
        _in("status", MemberStatus, "status"),
        _in("origin", MemberOrigin, "origin"),
        _in("channel", EnrollmentChannel, "channel"),
        CheckConstraint(
            "(origin = 'recruiter') = (recruited_by_member_id IS NOT NULL)", name="recruiter"
        ),
        CheckConstraint("depth >= 0", name="depth"),
        {"schema": SCHEMA},
    )

    person_id: uuid.UUID = _fk("people.persons.id")
    enrolled_on: date = Field(sa_type=Date)
    level_id: uuid.UUID = _fk(f"{SCHEMA}.participation_levels.id")
    recruited_by_member_id: uuid.UUID | None = _fk(f"{SCHEMA}.members.id", nullable=True)
    origin: str = Field(sa_type=Text)
    origin_detail: str | None = Field(default=None, max_length=300)
    registered_by_user_id: uuid.UUID | None = _fk("identity.users.id", nullable=True)
    channel: str = Field(sa_type=Text)
    status: str = Field(sa_type=Text)
    status_reason: str | None = Field(default=None, max_length=500)
    validated_by_user_id: uuid.UUID | None = _fk("identity.users.id", nullable=True)
    validated_at: datetime | None = Field(default=None, sa_type=TZ)
    left_on: date | None = Field(default=None, sa_type=Date)
    referral_code: str = Field(max_length=32, unique=True)
    tree_id: int = Field(sa_column=Column(BigInteger, nullable=False, unique=True))
    path: str = Field(sa_column=Column(Ltree(), nullable=False))
    depth: int
    state_id: uuid.UUID = _fk("geography.states.id")
    section_id: uuid.UUID = _fk("geography.sections.id")
    consent_id: uuid.UUID | None = _fk(
        "people.privacy_consents.id", nullable=True, ondelete="SET NULL"
    )


class MemberLevelChange(BusinessTable, table=True):
    __tablename__ = "member_level_changes"
    __table_args__ = ({"schema": SCHEMA},)

    member_id: uuid.UUID = _fk(f"{SCHEMA}.members.id")
    from_level_id: uuid.UUID = _fk(f"{SCHEMA}.participation_levels.id")
    to_level_id: uuid.UUID = _fk(f"{SCHEMA}.participation_levels.id")
    changed_by_user_id: uuid.UUID | None = _fk("identity.users.id", nullable=True)
    changed_at: datetime = Field(sa_type=TZ)
    reason: str | None = Field(default=None, max_length=500)


class MemberRecruiterChange(BusinessTable, table=True):
    __tablename__ = "member_recruiter_changes"
    __table_args__ = ({"schema": SCHEMA},)

    member_id: uuid.UUID = _fk(f"{SCHEMA}.members.id")
    from_member_id: uuid.UUID | None = _fk(f"{SCHEMA}.members.id", nullable=True)
    to_member_id: uuid.UUID = _fk(f"{SCHEMA}.members.id")
    changed_by_user_id: uuid.UUID | None = _fk("identity.users.id", nullable=True)
    changed_at: datetime = Field(sa_type=TZ)
    reason: str = Field(max_length=500)
    subtree_size: int


class UserBranchScope(BusinessTable, table=True):
    """Branch scope (D-83): the user sees the whole network under `member_id`, across states."""

    __tablename__ = "user_branch_scopes"
    __table_args__ = (
        Index(
            "uq_user_branch_scopes_user_member",
            "user_id",
            "member_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    user_id: uuid.UUID = _fk("identity.users.id", ondelete="CASCADE")
    member_id: uuid.UUID = _fk(f"{SCHEMA}.members.id")


class NetworkChange(SQLModel, table=True):
    """Outbox of changes the aggregates job applies (phase 3). bigint PK: massive and never
    referenced (D-03). Not audited: each change is already audited on its own row."""

    __tablename__ = "network_changes"
    __table_args__ = (
        Index("ix_network_changes_pending", "id", postgresql_where=text("processed_at IS NULL")),
        {"schema": SCHEMA},
    )
    __audit__: ClassVar[bool] = False

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    kind: str = Field(sa_type=Text)
    member_id: uuid.UUID | None = None
    # Ancestor chains whose counters change (ltree paths as text).
    paths: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    created_at: datetime = Field(sa_column=Column(TZ, nullable=False, server_default=text("now()")))
    processed_at: datetime | None = Field(default=None, sa_type=TZ)
