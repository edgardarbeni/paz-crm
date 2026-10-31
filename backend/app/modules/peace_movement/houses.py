"""Peace Houses: opening with credit, members, consolidation, roles, meetings with guests, photos
and the host's consent to publish the location (docs/modules/peace-movement.md, D-85, D-92).

A house is visible if its section is in the user's scope or if its host, contact or opener is
a visible member (member scope, D-83).
"""

import json
import struct
import uuid
from datetime import UTC, date, datetime
from typing import Any

from geoalchemy2 import WKBElement, WKTElement
from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.core.audit import record_access
from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.core.storage import ObjectStorage
from app.modules.geography import service as geography
from app.modules.identity.services.scopes import GeoScope
from app.modules.party_structure import access as structure
from app.modules.peace_movement import catalog
from app.modules.peace_movement.members import Actor, visible_member
from app.modules.peace_movement.models import (
    CURRENT_HOUSE_STATUSES,
    HouseMemberSource,
    HouseStatus,
    Member,
    MemberStatus,
    NetworkChange,
    PeaceHouse,
    PeaceHouseCreditChange,
    PeaceHouseMeeting,
    PeaceHouseMeetingAttendee,
    PeaceHouseMember,
    PeaceHousePhoto,
)
from app.modules.peace_movement.schemas import CreditIn, HouseIn, HouseUpdate, MeetingIn
from app.modules.peace_movement.scope import in_branch, member_visibility
from app.modules.people import service as people
from app.modules.people.models import Person
from app.modules.people.schemas import ContactIn, PersonCreate

ADDRESS_CONTEXT = "peace_movement.peace_houses.address"
LOCATION_NOTICE = "peace_house_location"
MIN_MEMBERS_TO_OPEN = 2
# Rounding of the clear point: 3 decimals ≈ 110 m (D-85).
APPROX_DECIMALS = 3
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PHOTO_MAX_BYTES = 10 * 1024 * 1024
EWKB_SRID_FLAG = 0x20000000
UNRESTRICTED = GeoScope(user_id=uuid.UUID(int=0), unrestricted=True)


# --- visibility -------------------------------------------------------------------------------


def house_visibility(geo: GeoScope) -> ColumnElement[bool] | None:
    if geo.unrestricted:
        return None
    member = aliased(Member)
    visible_member_filter = member_visibility(geo, member)
    assert visible_member_filter is not None  # noqa: S101 - restricted scopes always filter
    role_visible = exists().where(
        col(member.id).in_(
            [
                col(PeaceHouse.host_member_id),
                col(PeaceHouse.contact_member_id),
                col(PeaceHouse.opened_by_member_id),
            ]
        ),
        visible_member_filter,
    )
    geographic = geo.sections_filter(col(PeaceHouse.section_id))
    assert geographic is not None  # noqa: S101
    return or_(geographic, role_visible)


def _visible(geo: GeoScope) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [col(PeaceHouse.deleted_at).is_(None)]
    scoped = house_visibility(geo)
    if scoped is not None:
        filters.append(scoped)
    return filters


async def visible_house(
    db: AsyncSession, geo: GeoScope, house_id: uuid.UUID, *, for_update: bool = False
) -> PeaceHouse:
    statement = select(PeaceHouse).where(col(PeaceHouse.id) == house_id, *_visible(geo))
    if for_update:
        statement = statement.with_for_update(of=PeaceHouse)
    house = (await db.execute(statement)).scalar_one_or_none()
    if house is None:
        raise NotFoundError("Casa de Paz no encontrada.")
    return house


def _ensure_current(house: PeaceHouse) -> None:
    if house.status not in CURRENT_HOUSE_STATUSES:
        raise ConflictError("La Casa de Paz está cerrada.")


async def _active_member(
    db: AsyncSession, geo: GeoScope, member_id: uuid.UUID, role: str
) -> Member:
    member = await visible_member(db, geo, member_id)
    if member.status != MemberStatus.ACTIVE:
        raise ConflictError(f"El {role} debe ser un pacificador activo.")
    return member


# --- helpers ----------------------------------------------------------------------------------


def approx_point(house: PeaceHouse) -> tuple[float, float]:
    """(lon, lat) of the stored point without Shapely: a WKT element right after writing it,
    (E)WKB (bytes or hex) once loaded from the database."""
    location = house.location
    if isinstance(location, WKTElement):
        lon_text, lat_text = str(location.data).strip()[6:-1].split()
        return float(lon_text), float(lat_text)
    data = location.data if isinstance(location, WKBElement) else location
    raw = bytes.fromhex(data) if isinstance(data, str) else bytes(data)
    order = "<" if raw[0] == 1 else ">"
    (kind,) = struct.unpack(f"{order}I", raw[1:5])
    offset = 9 if kind & EWKB_SRID_FLAG else 5
    lon, lat = struct.unpack(f"{order}dd", raw[offset : offset + 16])
    return float(lon), float(lat)


def decoded_address(crypto: people.Crypto, house: PeaceHouse) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(
        crypto.cipher.decrypt(house.address_ciphertext, context=ADDRESS_CONTEXT)
    )
    return value


async def current_members(db: AsyncSession, house_id: uuid.UUID) -> list[PeaceHouseMember]:
    rows = await db.execute(
        select(PeaceHouseMember)
        .where(
            col(PeaceHouseMember.house_id) == house_id,
            col(PeaceHouseMember.left_on).is_(None),
            col(PeaceHouseMember.deleted_at).is_(None),
        )
        .order_by(col(PeaceHouseMember.joined_on), col(PeaceHouseMember.created_at))
    )
    return list(rows.scalars())


async def member_counts(db: AsyncSession, house_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not house_ids:
        return {}
    rows = await db.execute(
        select(col(PeaceHouseMember.house_id), func.count())
        .where(
            col(PeaceHouseMember.house_id).in_(house_ids),
            col(PeaceHouseMember.left_on).is_(None),
            col(PeaceHouseMember.deleted_at).is_(None),
        )
        .group_by(col(PeaceHouseMember.house_id))
    )
    return {house_id: int(count) for house_id, count in rows.all()}


def _join(house: PeaceHouse, member_id: uuid.UUID, source: HouseMemberSource) -> PeaceHouseMember:
    return PeaceHouseMember(
        house_id=pk(house), member_id=member_id, joined_on=date.today(), source=source
    )


async def _ensure_member_row(
    db: AsyncSession, house: PeaceHouse, member_id: uuid.UUID, source: HouseMemberSource
) -> None:
    present = {row.member_id for row in await current_members(db, pk(house))}
    if member_id not in present:
        db.add(_join(house, member_id, source))
        await db.flush()


async def house_changed(db: AsyncSession, *member_ids: uuid.UUID | None) -> None:
    """Outbox entry for the house counters of the credited members (aggregates, phase 3)."""
    for member_id in {m for m in member_ids if m is not None}:
        member = await db.get(Member, member_id)
        if member is not None:
            db.add(
                NetworkChange(
                    kind="house_changed",
                    member_id=member_id,
                    paths=[member.path],
                    created_at=datetime.now(UTC),
                )
            )


async def sync_status(db: AsyncSession, house: PeaceHouse) -> None:
    """Consolidated while current members reach the goal in force in the house's state; back to
    open if they drop below it (D-92). The first consolidation date is kept."""
    if house.status not in CURRENT_HOUSE_STATUSES:
        return
    before = house.status
    count = len(await current_members(db, pk(house)))
    goal = await catalog.house_goal_for(db, house.state_id)
    reached = goal is not None and count >= goal.member_goal
    if reached and house.status == HouseStatus.OPEN:
        house.status = HouseStatus.CONSOLIDATED
        house.consolidated_on = date.today()
        house.first_consolidated_on = house.first_consolidated_on or date.today()
    elif not reached and house.status == HouseStatus.CONSOLIDATED:
        house.status = HouseStatus.OPEN
        house.consolidated_on = None
    if house.status != before:
        await house_changed(db, house.credited_member_id)
    await db.flush()


# --- commands ---------------------------------------------------------------------------------


async def open_house(
    db: AsyncSession, crypto: people.Crypto, actor: Actor, body: HouseIn, *, can_link: bool
) -> PeaceHouse:
    """The credit goes to whoever opens it (D-103): a member of any level, or a party structure
    seat the user holds (then regardless of the geography). With neither, it is pending."""
    opener = (
        await _active_member(db, actor.geo, body.opened_by_member_id, "pacificador que abre")
        if body.opened_by_member_id
        else None
    )
    position_id = body.opened_by_position_id
    if position_id is not None:
        await _ensure_own_seat(db, actor, position_id, can_link=can_link)
    host = await _active_member(db, actor.geo, body.host_member_id, "anfitrión")
    contact = await _active_member(db, actor.geo, body.contact_member_id, "contacto")
    found = await geography.locate(
        db, UNRESTRICTED, longitude=body.address.longitude, latitude=body.address.latitude
    )
    section_id = uuid.UUID(str(found["section"]["id"]))
    in_scope = await _section_in_scope(db, actor.geo, section_id) or (
        opener is not None and await in_branch(db, actor.geo, opener)
    )
    if position_id is None and not in_scope:
        raise ForbiddenError("La casa queda fuera de tu alcance geográfico.")

    wanted = list(dict.fromkeys([pk(host), pk(contact), *body.member_ids]))
    for member_id in wanted:
        if member_id not in {pk(host), pk(contact)}:
            await _active_member(db, actor.geo, member_id, "integrante")
    if len(wanted) < MIN_MEMBERS_TO_OPEN:
        raise BadRequestError(
            f"Una Casa de Paz se abre con al menos {MIN_MEMBERS_TO_OPEN} integrantes."
        )

    private = body.address.model_dump(exclude_none=True)
    blob = crypto.cipher.encrypt(json.dumps(private, ensure_ascii=False), context=ADDRESS_CONTEXT)
    lon = round(body.address.longitude, APPROX_DECIMALS)
    lat = round(body.address.latitude, APPROX_DECIMALS)
    credited_member = pk(opener) if opener is not None else None
    house = PeaceHouse(
        name=body.name,
        schedule=[slot.model_dump() for slot in body.schedule],
        capacity=body.capacity,
        address_ciphertext=blob,
        key_version=crypto.cipher.key_version(blob),
        location=WKTElement(f"POINT({lon} {lat})", srid=4326),
        state_id=uuid.UUID(str(found["state"]["id"])),
        municipality_id=uuid.UUID(str(found["municipality"]["id"])),
        section_id=section_id,
        host_member_id=pk(host),
        contact_member_id=pk(contact),
        opened_by_member_id=credited_member,
        opened_by_position_id=position_id,
        credited_member_id=credited_member,
        credited_position_id=position_id,
        status=HouseStatus.OPEN,
        opened_on=date.today(),
    )
    db.add(house)
    await db.flush()
    for member_id in wanted:
        role = member_id in {pk(host), pk(contact)}
        db.add(
            _join(
                house, member_id, HouseMemberSource.ROLE if role else HouseMemberSource.ASSIGNMENT
            )
        )
    await db.flush()
    await sync_status(db, house)
    await house_changed(db, credited_member)
    await db.commit()
    return house


async def _section_in_scope(db: AsyncSession, geo: GeoScope, section_id: uuid.UUID) -> bool:
    return await geo.contains_section(db, section_id)


async def update_house(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID, body: HouseUpdate
) -> PeaceHouse:
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    _ensure_current(house)
    fields = body.model_dump(exclude_unset=True, exclude={"host_member_id", "contact_member_id"})
    if "schedule" in fields and body.schedule is not None:
        fields["schedule"] = [slot.model_dump() for slot in body.schedule]
    for key, value in fields.items():
        setattr(house, key, value)
    for attribute, role in (("host_member_id", "anfitrión"), ("contact_member_id", "contacto")):
        member_id = getattr(body, attribute)
        if member_id is None:
            continue
        member = await _active_member(db, actor.geo, member_id, role)
        setattr(house, attribute, pk(member))
        await _ensure_member_row(db, house, pk(member), HouseMemberSource.ROLE)
    house.needs_reassignment = house.host_member_id is None or house.contact_member_id is None
    await db.flush()
    await sync_status(db, house)
    await db.commit()
    return house


async def close_house(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID, reason: str
) -> PeaceHouse:
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    _ensure_current(house)
    house.status = HouseStatus.CLOSED
    house.closed_on = date.today()
    house.consolidated_on = None
    house.status_reason = reason
    await house_changed(db, house.credited_member_id)
    await db.commit()
    return house


async def _ensure_own_seat(
    db: AsyncSession, actor: Actor, position_id: uuid.UUID, *, can_link: bool
) -> None:
    if not can_link:
        raise ForbiddenError("No tienes el permiso «peace_movement.house.link».")
    if position_id not in await structure.current_seats_of_user(db, actor.user_id):
        raise ForbiddenError("Solo abres o enlazas casas con un cargo que ocupas.")


def _credit_change(
    house: PeaceHouse,
    *,
    to_member: uuid.UUID | None,
    to_position: uuid.UUID | None,
    by: uuid.UUID | None,
    reason: str,
) -> PeaceHouseCreditChange:
    return PeaceHouseCreditChange(
        house_id=pk(house),
        from_member_id=house.credited_member_id,
        from_position_id=house.credited_position_id,
        to_member_id=to_member,
        to_position_id=to_position,
        changed_by_user_id=by,
        changed_at=datetime.now(UTC),
        reason=reason,
    )


async def reassign_credit(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID, body: CreditIn
) -> PeaceHouse:
    """Only by hand, with a reason: to an active member of any level or to a held seat
    (D-103). The credit never follows later promotions."""
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    to_member: uuid.UUID | None = None
    to_position: uuid.UUID | None = None
    if body.member_id is not None:
        to_member = pk(
            await _active_member(db, actor.geo, body.member_id, "pacificador acreditado")
        )
    else:
        assert body.position_id is not None  # noqa: S101 - validated by the schema
        if not await structure.seat_is_held(db, body.position_id):
            raise ConflictError("El asiento está vacante: el crédito va a un cargo ocupado.")
        to_position = body.position_id
    if (to_member, to_position) == (house.credited_member_id, house.credited_position_id):
        raise ConflictError("La casa ya está acreditada a ese destinatario.")
    db.add(
        _credit_change(
            house,
            to_member=to_member,
            to_position=to_position,
            by=actor.user_id,
            reason=body.reason,
        )
    )
    await house_changed(db, house.credited_member_id, to_member)
    house.credited_member_id = to_member
    house.credited_position_id = to_position
    await db.commit()
    return house


def _pending() -> list[ColumnElement[bool]]:
    return [
        col(PeaceHouse.credited_member_id).is_(None),
        col(PeaceHouse.credited_position_id).is_(None),
        col(PeaceHouse.status).in_(CURRENT_HOUSE_STATUSES),
        col(PeaceHouse.deleted_at).is_(None),
    ]


async def pending_houses(db: AsyncSession, params: PageParams) -> CursorPage[PeaceHouse]:
    """Tray of houses to link (D-103): every current house without credit, regardless of the
    geography, for whoever may link them with a seat."""
    sort = parse_sort(
        params.sort,
        allowed={"opened_on": col(PeaceHouse.opened_on), "name": col(PeaceHouse.name)},
        tiebreaker=col(PeaceHouse.id),
        default="opened_on",
    )
    page: CursorPage[PeaceHouse] = await paginate(
        db,
        select(PeaceHouse).where(*_pending()),
        sort=sort,
        limit=params.limit,
        cursor=params.cursor,
    )
    return page


async def link_house(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID, position_id: uuid.UUID, *, can_link: bool
) -> PeaceHouse:
    await _ensure_own_seat(db, actor, position_id, can_link=can_link)
    house = (
        await db.execute(
            select(PeaceHouse).where(col(PeaceHouse.id) == house_id, *_pending()).with_for_update()
        )
    ).scalar_one_or_none()
    if house is None:
        raise ConflictError("La casa no está en la bandeja: ya tiene crédito o no está vigente.")
    db.add(
        _credit_change(
            house,
            to_member=None,
            to_position=position_id,
            by=actor.user_id,
            reason="Enlazada desde la bandeja de casas por enlazar.",
        )
    )
    house.credited_position_id = position_id
    await db.commit()
    return house


async def add_member(
    db: AsyncSession,
    actor: Actor,
    house_id: uuid.UUID,
    member_id: uuid.UUID,
    source: HouseMemberSource = HouseMemberSource.ASSIGNMENT,
    *,
    commit: bool = True,
) -> PeaceHouseMember:
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    _ensure_current(house)
    member = await _active_member(db, actor.geo, member_id, "integrante")
    present = {row.member_id for row in await current_members(db, pk(house))}
    if pk(member) in present:
        raise ConflictError("El pacificador ya integra esta casa.")
    row = _join(house, pk(member), source)
    db.add(row)
    await db.flush()
    await sync_status(db, house)
    if commit:
        await db.commit()
    return row


async def remove_member(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    _ensure_current(house)
    if member_id in {house.host_member_id, house.contact_member_id}:
        raise ConflictError("Cambia primero al anfitrión o al contacto.")
    rows = [r for r in await current_members(db, pk(house)) if r.member_id == member_id]
    if not rows:
        raise NotFoundError("El pacificador no integra esta casa.")
    rows[0].left_on = date.today()
    await db.flush()
    await sync_status(db, house)
    await db.commit()


async def member_left(db: AsyncSession, member: Member) -> None:
    """The member left the movement or was withdrawn (ARCO): their memberships end, and if they
    were the host the contact takes the role, and vice versa; with neither, the house is flagged
    for reassignment (D-92). Runs in the caller's transaction."""
    member_id = pk(member)
    rows = await db.execute(
        select(PeaceHouseMember).where(
            col(PeaceHouseMember.member_id) == member_id,
            col(PeaceHouseMember.left_on).is_(None),
            col(PeaceHouseMember.deleted_at).is_(None),
        )
    )
    house_ids = set()
    for row in rows.scalars():
        row.left_on = date.today()
        house_ids.add(row.house_id)
    roles = await db.execute(
        select(PeaceHouse).where(
            or_(
                col(PeaceHouse.host_member_id) == member_id,
                col(PeaceHouse.contact_member_id) == member_id,
            ),
            col(PeaceHouse.status).in_(CURRENT_HOUSE_STATUSES),
            col(PeaceHouse.deleted_at).is_(None),
        )
    )
    for house in roles.scalars():
        if house.host_member_id == member_id:
            other = house.contact_member_id if house.contact_member_id != member_id else None
            house.host_member_id = other
            if house.contact_member_id == member_id:
                house.contact_member_id = None
        elif house.contact_member_id == member_id:
            house.contact_member_id = house.host_member_id
        house.needs_reassignment = house.host_member_id is None or house.contact_member_id is None
        house_ids.add(pk(house))
    # D-105: the credit of a member who leaves goes back to the tray of houses to link.
    credited = await db.execute(
        select(PeaceHouse).where(
            col(PeaceHouse.credited_member_id) == member_id,
            col(PeaceHouse.status).in_(CURRENT_HOUSE_STATUSES),
            col(PeaceHouse.deleted_at).is_(None),
        )
    )
    for house in credited.scalars():
        db.add(
            _credit_change(
                house,
                to_member=None,
                to_position=None,
                by=None,
                reason="Baja del pacificador acreditado: la casa pasa a la bandeja.",
            )
        )
        house.credited_member_id = None
        house_ids.add(pk(house))
    await db.flush()
    for house_id in house_ids:
        affected = await db.get(PeaceHouse, house_id)
        if affected is not None:
            await sync_status(db, affected)


# --- public location consent ------------------------------------------------------------------


async def record_location_consent(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID, *, channel: str, evidence_uri: str | None
) -> PeaceHouse:
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    if house.host_member_id is None:
        raise ConflictError("La casa no tiene anfitrión que pueda otorgar el consentimiento.")
    notice = await people.current_notice(db, LOCATION_NOTICE)
    if notice is None:
        raise ConflictError(
            "Carga el aviso para publicar la ubicación de las casas (código "
            f"«{LOCATION_NOTICE}») antes de registrar el consentimiento."
        )
    host = await db.get(Member, house.host_member_id)
    assert host is not None  # noqa: S101 - FK
    consent = await people.record_consent(
        db, host.person_id, notice, channel=channel, evidence_uri=evidence_uri
    )
    house.public_location_consent_id = consent.id
    await db.commit()
    return house


async def revoke_location_consent(
    db: AsyncSession, actor: Actor, house_id: uuid.UUID
) -> PeaceHouse:
    house = await visible_house(db, actor.geo, house_id, for_update=True)
    house.public_location_consent_id = None
    await db.commit()
    return house


# --- meetings ---------------------------------------------------------------------------------


async def add_meeting(
    db: AsyncSession, crypto: people.Crypto, actor: Actor, house_id: uuid.UUID, body: MeetingIn
) -> PeaceHouseMeeting:
    house = await visible_house(db, actor.geo, house_id)
    _ensure_current(house)
    persons: dict[uuid.UUID, None] = {}
    for member_id in body.member_ids:
        member = await visible_member(db, actor.geo, member_id)
        persons[member.person_id] = None
    for person_id in body.guest_person_ids:
        persons[pk(await people.visible_person(db, actor.geo, person_id))] = None
    for guest in body.guests:
        view = await people.build_person(
            db,
            crypto,
            actor.geo,
            PersonCreate(
                given_names=guest.given_names,
                paternal_surname=guest.paternal_surname,
                maternal_surname=guest.maternal_surname,
                contacts=[ContactIn(contact_type="mobile", value=guest.mobile, is_primary=True)]
                if guest.mobile
                else [],
            ),
            can_accept_incoherence=False,
        )
        persons[pk(view.person)] = None
    meeting = PeaceHouseMeeting(
        house_id=pk(house), held_at=body.held_at, topic=body.topic, notes=body.notes
    )
    db.add(meeting)
    await db.flush()
    db.add_all(
        PeaceHouseMeetingAttendee(meeting_id=pk(meeting), person_id=person_id)
        for person_id in persons
    )
    await db.commit()
    return meeting


async def list_meetings(
    db: AsyncSession, geo: GeoScope, house_id: uuid.UUID, params: PageParams
) -> CursorPage[PeaceHouseMeeting]:
    house = await visible_house(db, geo, house_id)
    statement = select(PeaceHouseMeeting).where(
        col(PeaceHouseMeeting.house_id) == pk(house), col(PeaceHouseMeeting.deleted_at).is_(None)
    )
    sort = parse_sort(
        params.sort,
        allowed={"held_at": col(PeaceHouseMeeting.held_at)},
        tiebreaker=col(PeaceHouseMeeting.id),
        default="-held_at",
    )
    page: CursorPage[PeaceHouseMeeting] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def attendance(
    db: AsyncSession, meeting_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[Person, uuid.UUID | None]]]:
    """Attendees per meeting: (person, member id or None for guests)."""
    if not meeting_ids:
        return {}
    rows = await db.execute(
        select(PeaceHouseMeetingAttendee, Person, col(Member.id))
        .join(Person, col(Person.id) == col(PeaceHouseMeetingAttendee.person_id))
        .outerjoin(
            Member,
            (col(Member.person_id) == col(Person.id)) & col(Member.deleted_at).is_(None),
        )
        .where(
            col(PeaceHouseMeetingAttendee.meeting_id).in_(meeting_ids),
            col(PeaceHouseMeetingAttendee.deleted_at).is_(None),
        )
        .order_by(col(Person.paternal_surname), col(Person.given_names))
    )
    result: dict[uuid.UUID, list[tuple[Person, uuid.UUID | None]]] = {m: [] for m in meeting_ids}
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for attendee, person, member_id in rows.all():
        key = (attendee.meeting_id, attendee.person_id)
        if key in seen:  # a person with several memberships (e.g. left and enrolled again)
            continue
        seen.add(key)
        result[attendee.meeting_id].append((person, member_id))
    return result


async def get_meeting(
    db: AsyncSession, geo: GeoScope, house_id: uuid.UUID, meeting_id: uuid.UUID
) -> PeaceHouseMeeting:
    house = await visible_house(db, geo, house_id)
    meeting = await db.get(PeaceHouseMeeting, meeting_id)
    if meeting is None or meeting.house_id != pk(house) or meeting.deleted_at is not None:
        raise NotFoundError("Reunión no encontrada.")
    return meeting


# --- photos -----------------------------------------------------------------------------------


async def add_photo(
    db: AsyncSession,
    storage: ObjectStorage,
    actor: Actor,
    house_id: uuid.UUID,
    *,
    data: bytes,
    content_type: str,
    caption: str | None,
) -> PeaceHousePhoto:
    house = await visible_house(db, actor.geo, house_id)
    extension = PHOTO_TYPES.get(content_type)
    if extension is None:
        raise BadRequestError("La foto debe ser JPEG, PNG o WebP.")
    if not data or len(data) > PHOTO_MAX_BYTES:
        raise BadRequestError("La foto debe pesar entre 1 byte y 10 MB.")
    key = ObjectStorage.new_key(f"peace_movement/houses/{pk(house)}", extension)
    await storage.put(key, data, content_type)
    photo = PeaceHousePhoto(
        house_id=pk(house),
        storage_key=key,
        content_type=content_type,
        size_bytes=len(data),
        caption=caption,
        uploaded_by_user_id=actor.user_id,
    )
    db.add(photo)
    await db.commit()
    return photo


async def list_photos(
    db: AsyncSession, geo: GeoScope, house_id: uuid.UUID
) -> list[PeaceHousePhoto]:
    house = await visible_house(db, geo, house_id)
    rows = await db.execute(
        select(PeaceHousePhoto)
        .where(
            col(PeaceHousePhoto.house_id) == pk(house), col(PeaceHousePhoto.deleted_at).is_(None)
        )
        .order_by(col(PeaceHousePhoto.created_at).desc())
    )
    return list(rows.scalars())


async def delete_photo(
    db: AsyncSession, storage: ObjectStorage, actor: Actor, house_id: uuid.UUID, photo_id: uuid.UUID
) -> None:
    house = await visible_house(db, actor.geo, house_id)
    photo = await db.get(PeaceHousePhoto, photo_id)
    if photo is None or photo.house_id != pk(house) or photo.deleted_at is not None:
        raise NotFoundError("Foto no encontrada.")
    photo.deleted_at = datetime.now(UTC)
    await db.commit()
    await storage.delete(photo.storage_key)


# --- reads ------------------------------------------------------------------------------------

_SORTS = {"opened_on": col(PeaceHouse.opened_on), "name": col(PeaceHouse.name)}


async def search_houses(
    db: AsyncSession,
    geo: GeoScope,
    params: PageParams,
    *,
    status: str | None = None,
    state_id: uuid.UUID | None = None,
    credited_member_id: uuid.UUID | None = None,
    credit_pending: bool | None = None,
    needs_reassignment: bool | None = None,
    publishable: bool | None = None,
) -> CursorPage[PeaceHouse]:
    statement = select(PeaceHouse).where(*_visible(geo))
    if status:
        statement = statement.where(col(PeaceHouse.status) == status)
    if state_id:
        statement = statement.where(col(PeaceHouse.state_id) == state_id)
    if credited_member_id:
        statement = statement.where(col(PeaceHouse.credited_member_id) == credited_member_id)
    if credit_pending is not None:
        pending = col(PeaceHouse.credited_member_id).is_(None) & col(
            PeaceHouse.credited_position_id
        ).is_(None)
        statement = statement.where(pending if credit_pending else ~pending)
    if needs_reassignment is not None:
        statement = statement.where(col(PeaceHouse.needs_reassignment).is_(needs_reassignment))
    if publishable is not None:
        consented = col(PeaceHouse.public_location_consent_id).is_not(None)
        statement = statement.where(consented if publishable else ~consented)
    sort = parse_sort(
        params.sort, allowed=_SORTS, tiebreaker=col(PeaceHouse.id), default="-opened_on"
    )
    page: CursorPage[PeaceHouse] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def read_house(
    db: AsyncSession, geo: GeoScope, house_id: uuid.UUID, *, unmasked: bool
) -> PeaceHouse:
    house = await visible_house(db, geo, house_id)
    await record_access(
        db,
        action="read",
        entity_table="peace_movement.peace_houses",
        entity_id=str(house.id),
        details={"unmasked": unmasked},
    )
    await db.commit()
    return house


async def progress(
    db: AsyncSession, house: PeaceHouse, count: int
) -> tuple[int | None, int | None]:
    goal = await catalog.house_goal_for(db, house.state_id)
    if goal is None:
        return None, None
    return goal.member_goal, count * 100 // goal.member_goal


MAP_LIMIT = 10_000


async def map_points(
    db: AsyncSession, geo: GeoScope, *, status: str | None = None, state_id: uuid.UUID | None = None
) -> tuple[list[dict[str, Any]], bool]:
    """Visible houses as GeoJSON points at their approximate location (D-85), capped."""
    statement = select(
        col(PeaceHouse.id),
        col(PeaceHouse.name),
        col(PeaceHouse.status),
        col(PeaceHouse.public_location_consent_id),
        func.ST_X(col(PeaceHouse.location)),
        func.ST_Y(col(PeaceHouse.location)),
    ).where(*_visible(geo))
    if status:
        statement = statement.where(col(PeaceHouse.status) == status)
    else:
        statement = statement.where(col(PeaceHouse.status).in_(CURRENT_HOUSE_STATUSES))
    if state_id:
        statement = statement.where(col(PeaceHouse.state_id) == state_id)
    rows = (await db.execute(statement.limit(MAP_LIMIT + 1))).all()
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {
                "id": str(house_id),
                "name": name,
                "status": house_status,
                "publishable": consent is not None,
            },
        }
        for house_id, name, house_status, consent, lon, lat in rows[:MAP_LIMIT]
    ]
    return features, len(rows) > MAP_LIMIT
