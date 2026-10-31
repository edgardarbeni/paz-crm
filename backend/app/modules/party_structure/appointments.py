"""Seats and appointments (phase 2, D-108).

- A seat (`positions`) exists for every position type of every current body; circumscription
  positions have one seat per circumscription.
- A seat has at most one current appointment; the history is never deleted.
- Derived seats (Presídium) are never appointed: their holder is the current holder of their
  source seat, fixed or chosen in each period (D-105).
- Delegated administration (D-105, D-108): an appointment is managed through a grant whose
  level is higher than the seat's and whose scope contains the seat's territory. A grant from an
  appointment has the level of that position; a manual grant, the level of its scope, and a
  national manual grant (or superadmin) manages every level.
"""

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from enum import IntEnum

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.modules.identity.models import GrantOrigin, ScopeLevel, UserGrantScope
from app.modules.identity.services.access import Access, Grant
from app.modules.identity.services.scopes import (
    GeoScope,
    active_framework,
    ensure_node_within,
)
from app.modules.party_structure.models import (
    Appointment,
    AppointmentKind,
    Body,
    BodyType,
    DerivedChoice,
    EndReason,
    Position,
    PositionDerivation,
    PositionIncompatibility,
    PositionType,
    ScopeRule,
    TerritorialLevel,
)
from app.modules.party_structure.permissions import StructurePerm
from app.modules.people.models import Person

# The catalog itself says «Cinco Secretarías de Circunscripción» (docs/reference/cargos_paz.md).
CIRCUMSCRIPTIONS = 5


class Level(IntEnum):
    """Order for delegated administration (D-105)."""

    COORDINATION = 1
    LOCAL = 2  # federal district, local district, municipality and its coordinations
    STATE = 3
    CIRCUMSCRIPTION = 4
    NATIONAL = 5
    EVERYTHING = 6  # superadmin or a national manual grant: also national seats


_SCOPE_LEVEL = {
    ScopeLevel.NATIONAL: Level.EVERYTHING,
    ScopeLevel.ELECTORAL_REGION: Level.CIRCUMSCRIPTION,
    ScopeLevel.STATE: Level.STATE,
    ScopeLevel.FEDERAL_DISTRICT: Level.LOCAL,
    ScopeLevel.LOCAL_DISTRICT: Level.LOCAL,
    ScopeLevel.MUNICIPALITY: Level.LOCAL,
    ScopeLevel.SECTION: Level.COORDINATION,
}


@dataclass(frozen=True, slots=True)
class Seat:
    position: Position
    position_type: PositionType
    body: Body
    body_type: BodyType

    @property
    def level(self) -> Level:
        if self.position_type.scope_rule == ScopeRule.CIRCUMSCRIPTION:
            return Level.CIRCUMSCRIPTION
        if self.position_type.scope_rule == ScopeRule.NATIONAL:
            return Level.NATIONAL
        return {
            TerritorialLevel.NATIONAL: Level.NATIONAL,
            TerritorialLevel.STATE: Level.STATE,
            TerritorialLevel.DISTRICT: Level.LOCAL,
            TerritorialLevel.MUNICIPAL: Level.LOCAL,
            TerritorialLevel.COORDINATION: Level.COORDINATION,
        }[TerritorialLevel(self.body_type.territorial_level)]


# --- seats ------------------------------------------------------------------------------------


async def ensure_seats(db: AsyncSession, body: Body) -> None:
    """Creates the missing seats of a current body (caller commits)."""
    await db.execute(
        text(
            "INSERT INTO party_structure.positions (body_id, position_type_id, region_number) "
            "SELECT b.id, p.id, r.n FROM party_structure.bodies b "
            "JOIN party_structure.position_types p ON p.body_type_id = b.body_type_id "
            "AND p.deleted_at IS NULL "
            "CROSS JOIN LATERAL (SELECT generate_series(1, :regions) AS n "
            "WHERE p.scope_rule = 'circumscription' "
            "UNION ALL SELECT NULL WHERE p.scope_rule <> 'circumscription') r "
            "WHERE b.id = :body AND NOT EXISTS (SELECT 1 FROM party_structure.positions x "
            "WHERE x.body_id = b.id AND x.position_type_id = p.id AND x.deleted_at IS NULL "
            "AND coalesce(x.region_number, 0) = coalesce(r.n, 0))"
        ),
        {"body": pk(body), "regions": CIRCUMSCRIPTIONS},
    )


async def ensure_seats_for_type(db: AsyncSession, position_type: PositionType) -> None:
    """A new position type gets a seat in every current body of its type (caller commits)."""
    bodies = await db.execute(
        select(Body).where(
            col(Body.body_type_id) == position_type.body_type_id,
            col(Body.dissolved_on).is_(None),
            col(Body.deleted_at).is_(None),
        )
    )
    for body in bodies.scalars():
        await ensure_seats(db, body)


async def load_seat(db: AsyncSession, position_id: uuid.UUID) -> Seat:
    row = (
        await db.execute(
            select(Position, PositionType, Body, BodyType)
            .join(PositionType, col(PositionType.id) == col(Position.position_type_id))
            .join(Body, col(Body.id) == col(Position.body_id))
            .join(BodyType, col(BodyType.id) == col(Body.body_type_id))
            .where(col(Position.id) == position_id, col(Position.deleted_at).is_(None))
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Asiento no encontrado.")
    return Seat(*row)


async def seats_of(db: AsyncSession, body_id: uuid.UUID) -> list[Seat]:
    rows = await db.execute(
        select(Position, PositionType, Body, BodyType)
        .join(PositionType, col(PositionType.id) == col(Position.position_type_id))
        .join(Body, col(Body.id) == col(Position.body_id))
        .join(BodyType, col(BodyType.id) == col(Body.body_type_id))
        .where(col(Position.body_id) == body_id, col(Position.deleted_at).is_(None))
        .order_by(col(PositionType.sort_order), col(Position.region_number))
    )
    return [Seat(*row) for row in rows.all()]


async def current_appointments(
    db: AsyncSession, position_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Appointment]:
    if not position_ids:
        return {}
    rows = await db.execute(
        select(Appointment).where(
            col(Appointment.position_id).in_(position_ids),
            col(Appointment.ended_on).is_(None),
            col(Appointment.deleted_at).is_(None),
        )
    )
    return {row.position_id: row for row in rows.scalars()}


# --- territory and delegated administration ---------------------------------------------------


async def node_of(db: AsyncSession, table: str, where: str, value: int) -> uuid.UUID:
    framework_id = await active_framework(db)
    found = (
        await db.execute(
            text(
                f"SELECT id FROM geography.{table} WHERE framework_id = :fw "  # noqa: S608
                f"AND is_active AND {where} = :value"
            ),
            {"fw": framework_id, "value": value},
        )
    ).scalar_one_or_none()
    if found is None:
        raise BadRequestError("El territorio del asiento no existe en el marco geográfico activo.")
    node: uuid.UUID = found
    return node


async def ensure_seat_within(db: AsyncSession, geo: GeoScope, seat: Seat) -> None:
    """The seat's whole territory is inside `geo` (national seats need an unrestricted one)."""
    if geo.unrestricted:
        return
    if seat.level == Level.CIRCUMSCRIPTION:
        assert seat.position.region_number is not None  # noqa: S101 - one seat per region
        node = await node_of(db, "electoral_regions", "region_number", seat.position.region_number)
        await ensure_node_within(db, geo, ScopeLevel.ELECTORAL_REGION, node)
        return
    if seat.body_type.coordination_kind is not None:
        from app.modules.party_structure import coordinations  # noqa: PLC0415 - cycle

        coordination = await coordinations.coordination_of_seat(db, seat)
        assert coordination is not None  # noqa: S101
        if seat.body.state_code is None:  # spans several states: national level only
            raise ForbiddenError(
                "Solo el nivel nacional administra coordinaciones de varios estados."
            )
        nodes = await coordinations.current_nodes(db, coordination)
        if not await coordinations.nodes_within(db, geo, coordination.kind, nodes):
            raise ForbiddenError("La coordinación está fuera de tu alcance.")
        return
    body = seat.body
    for column, level in (
        ("municipality_id", ScopeLevel.MUNICIPALITY),
        ("federal_district_id", ScopeLevel.FEDERAL_DISTRICT),
        ("local_district_id", ScopeLevel.LOCAL_DISTRICT),
    ):
        if getattr(body, column) is not None:
            await ensure_node_within(db, geo, level, getattr(body, column))
            return
    if body.state_code is not None:
        node = await node_of(db, "states", "state_code", body.state_code)
        await ensure_node_within(db, geo, ScopeLevel.STATE, node)
        return
    raise ForbiddenError("Solo el nivel nacional administra los cargos nacionales.")


async def grant_level(db: AsyncSession, grant: Grant) -> Level:
    if grant.role.grants_all or grant.national:
        return Level.EVERYTHING
    if grant.origin == GrantOrigin.APPOINTMENT:
        source = (
            await db.execute(
                text(
                    "SELECT a.position_id FROM identity.user_grants g "
                    "JOIN party_structure.appointments a ON a.id = g.source_id WHERE g.id = :g"
                ),
                {"g": grant.id},
            )
        ).scalar_one_or_none()
        return (await load_seat(db, source)).level if source else Level.COORDINATION
    levels = (
        await db.execute(
            select(col(UserGrantScope.scope_level)).where(col(UserGrantScope.grant_id) == grant.id)
        )
    ).scalars()
    return max((_SCOPE_LEVEL[ScopeLevel(level)] for level in levels), default=Level.COORDINATION)


async def ensure_can_administer(
    db: AsyncSession, user_id: uuid.UUID, access: Access, seat: Seat
) -> None:
    """Some grant with `appointment.write` is above the seat's level and covers its territory."""
    permission = StructurePerm.APPOINTMENT_WRITE
    if access.grants_all:
        return
    too_low = False
    for grant in access.grants_for(permission):
        level = await grant_level(db, grant)
        if level <= seat.level:
            too_low = True
            continue
        geo = GeoScope(user_id=user_id, unrestricted=grant.national, grant_ids=(grant.id,))
        try:
            await ensure_seat_within(db, geo, seat)
        except ForbiddenError:
            continue
        return
    if too_low:
        raise ForbiddenError(
            "Solo administras cargos de un nivel inferior al tuyo y dentro de tu alcance."
        )
    raise ForbiddenError("El cargo está fuera de tu alcance.")


# --- appointments -----------------------------------------------------------------------------


def add_months(day: date, months: int) -> date:
    """`day` plus whole months, clamped to the last day of the target month (Feb 29 → 28)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def proposed_end(
    position_type: PositionType, kind: AppointmentKind, starts_on: date
) -> date | None:
    """`ends_on` proposed from the statute's term (editable); a delegate uses the months set
    for it (6 for the Delegación Estatal)."""
    if kind == AppointmentKind.DELEGATE and position_type.delegate_months:
        return add_months(starts_on, position_type.delegate_months) - timedelta(days=1)
    if position_type.term_years:
        return add_months(starts_on, 12 * position_type.term_years) - timedelta(days=1)
    if position_type.term_months:
        return add_months(starts_on, position_type.term_months) - timedelta(days=1)
    return None


async def _ensure_person(db: AsyncSession, person_id: uuid.UUID) -> None:
    person = await db.get(Person, person_id)
    if person is None or person.deleted_at is not None:
        raise NotFoundError("Persona no encontrada.")
    if person.curp_hash is None:
        raise BadRequestError("El titular de un cargo debe estar registrado con su CURP.")


async def _ensure_compatible(
    db: AsyncSession, person_id: uuid.UUID, position_type_id: uuid.UUID
) -> None:
    held = (
        select(col(Position.position_type_id))
        .join(Appointment, col(Appointment.position_id) == col(Position.id))
        .where(
            col(Appointment.person_id) == person_id,
            col(Appointment.ended_on).is_(None),
            col(Appointment.deleted_at).is_(None),
        )
    )
    clash = (
        await db.execute(
            select(PositionIncompatibility).where(
                col(PositionIncompatibility.deleted_at).is_(None),
                (
                    (col(PositionIncompatibility.position_type_a_id) == position_type_id)
                    & col(PositionIncompatibility.position_type_b_id).in_(held)
                )
                | (
                    (col(PositionIncompatibility.position_type_b_id) == position_type_id)
                    & col(PositionIncompatibility.position_type_a_id).in_(held)
                ),
            )
        )
    ).first()
    if clash is not None:
        raise ConflictError("La persona ocupa un cargo incompatible con este.")


async def _ensure_term_limit(
    db: AsyncSession, seat: Seat, person_id: uuid.UUID, kind: AppointmentKind
) -> None:
    """D-105: e.g. two consecutive periods at most for the cause coordinations."""
    limit = seat.position_type.max_consecutive_terms
    if limit is None or kind not in {AppointmentKind.ELECTED, AppointmentKind.DESIGNATED}:
        return
    previous = (
        await db.execute(
            select(Appointment)
            .where(
                col(Appointment.position_id) == pk(seat.position),
                col(Appointment.deleted_at).is_(None),
                col(Appointment.kind).in_([AppointmentKind.ELECTED, AppointmentKind.DESIGNATED]),
            )
            .order_by(col(Appointment.starts_on).desc())
            .limit(limit)
        )
    ).scalars()
    run = 0
    for appointment in previous:
        if appointment.person_id != person_id:
            break
        run += 1
    if run >= limit:
        raise ConflictError(
            f"Este cargo admite a lo más {limit} periodos consecutivos para la misma persona."
        )


async def appoint(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    position_id: uuid.UUID,
    person_id: uuid.UUID,
    kind: AppointmentKind,
    starts_on: date,
    ends_on: date | None,
    appointed_by: str | None,
    agreement_ref: str | None,
) -> Appointment:
    seat = await load_seat(db, position_id)
    if seat.body.dissolved_on is not None:
        raise ConflictError("El órgano está disuelto.")
    if seat.position_type.is_derived:
        raise ConflictError(
            "Este cargo se ocupa por derivación (Presídium): no acepta nombramientos."
        )
    await ensure_can_administer(db, user_id, access, seat)
    await _ensure_person(db, person_id)
    if kind == AppointmentKind.DELEGATE and not seat.position_type.delegate_months:
        raise BadRequestError("Este cargo no admite una delegación en funciones.")
    if (await current_appointments(db, [position_id])).get(position_id) is not None:
        raise ConflictError("El asiento está ocupado: termina primero el nombramiento vigente.")
    await _ensure_compatible(db, person_id, seat.position_type.id)  # type: ignore[arg-type]
    await _ensure_term_limit(db, seat, person_id, kind)
    end = ends_on if ends_on is not None else proposed_end(seat.position_type, kind, starts_on)
    if end is not None and end < starts_on:
        raise BadRequestError("El periodo termina antes de empezar.")
    appointment = Appointment(
        position_id=position_id,
        person_id=person_id,
        kind=kind,
        starts_on=starts_on,
        ends_on=end,
        appointed_by=appointed_by,
        agreement_ref=agreement_ref,
        role_id=seat.position_type.default_role_id,
    )
    db.add(appointment)
    seat.position.vacant_since = None
    try:
        await db.flush()
    except IntegrityError as error:  # a concurrent appointment took the seat
        await db.rollback()
        raise ConflictError("El asiento está ocupado.") from error
    await db.commit()
    return appointment


async def _appointment_seat(
    db: AsyncSession, appointment_id: uuid.UUID
) -> tuple[Appointment, Seat]:
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None or appointment.deleted_at is not None:
        raise NotFoundError("Nombramiento no encontrado.")
    return appointment, await load_seat(db, appointment.position_id)


async def end_appointment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    appointment_id: uuid.UUID,
    ended_on: date,
    reason: EndReason,
    notes: str | None,
) -> Appointment:
    appointment, seat = await _appointment_seat(db, appointment_id)
    await ensure_can_administer(db, user_id, access, seat)
    if appointment.ended_on is not None:
        raise ConflictError("El nombramiento ya terminó.")
    if ended_on < appointment.starts_on:
        raise BadRequestError("No puede terminar antes de empezar.")
    appointment.ended_on = ended_on
    appointment.end_reason = reason
    appointment.end_notes = notes
    seat.position.vacant_since = ended_on
    from app.modules.party_structure.access import revoke_access  # noqa: PLC0415 - cycle

    await revoke_access(db, appointment)
    await db.commit()
    return appointment


async def update_appointment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    appointment_id: uuid.UUID,
    ends_on: date | None,
    appointed_by: str | None,
    agreement_ref: str | None,
) -> Appointment:
    appointment, seat = await _appointment_seat(db, appointment_id)
    await ensure_can_administer(db, user_id, access, seat)
    if ends_on is not None and ends_on < appointment.starts_on:
        raise BadRequestError("El periodo termina antes de empezar.")
    appointment.ends_on = ends_on
    appointment.appointed_by = appointed_by
    appointment.agreement_ref = agreement_ref
    await db.commit()
    return appointment


async def history(db: AsyncSession, position_id: uuid.UUID) -> list[Appointment]:
    rows = await db.execute(
        select(Appointment)
        .where(col(Appointment.position_id) == position_id, col(Appointment.deleted_at).is_(None))
        .order_by(col(Appointment.starts_on).desc(), col(Appointment.created_at).desc())
    )
    return list(rows.scalars())


async def appointments_of_person(
    db: AsyncSession, person_id: uuid.UUID, *, current_only: bool
) -> list[Appointment]:
    statement = select(Appointment).where(
        col(Appointment.person_id) == person_id, col(Appointment.deleted_at).is_(None)
    )
    if current_only:
        statement = statement.where(col(Appointment.ended_on).is_(None))
    rows = await db.execute(statement.order_by(col(Appointment.starts_on).desc()))
    return list(rows.scalars())


# --- derived seats (Presídium) ----------------------------------------------------------------


async def sources_of(db: AsyncSession, position_type_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.execute(
        select(col(PositionDerivation.source_position_type_id)).where(
            col(PositionDerivation.position_type_id) == position_type_id,
            col(PositionDerivation.deleted_at).is_(None),
        )
    )
    return list(rows.scalars())


async def current_choice(db: AsyncSession, position_id: uuid.UUID) -> DerivedChoice | None:
    rows = await db.execute(
        select(DerivedChoice).where(
            col(DerivedChoice.position_id) == position_id,
            col(DerivedChoice.ends_on).is_(None),
            col(DerivedChoice.deleted_at).is_(None),
        )
    )
    return rows.scalar_one_or_none()


async def derived_holder(
    db: AsyncSession, seat: Seat
) -> tuple[uuid.UUID | None, Appointment | None]:
    """(source position type, its current appointment) of a derived seat. The source seat is the
    one of the source type in the same state (national bodies: the national one)."""
    sources = await sources_of(db, pk(seat.position_type))
    if len(sources) == 1:
        source = sources[0]
    else:
        choice = await current_choice(db, pk(seat.position))
        if choice is None:
            return None, None
        source = choice.source_position_type_id
    seat_id = (
        (
            await db.execute(
                select(col(Position.id))
                .join(Body, col(Body.id) == col(Position.body_id))
                .where(
                    col(Position.position_type_id) == source,
                    col(Position.deleted_at).is_(None),
                    col(Body.dissolved_on).is_(None),
                    col(Body.state_code).is_not_distinct_from(seat.body.state_code),
                )
            )
        )
        .scalars()
        .first()
    )
    if seat_id is None:
        return source, None
    return source, (await current_appointments(db, [seat_id])).get(seat_id)


async def choose_source(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    position_id: uuid.UUID,
    source_position_type_id: uuid.UUID,
    starts_on: date,
    agreement_ref: str | None,
) -> DerivedChoice:
    seat = await load_seat(db, position_id)
    sources = await sources_of(db, pk(seat.position_type))
    if len(sources) < 2:
        raise BadRequestError("Este cargo no se elige: su titular sale de un solo cargo.")
    if source_position_type_id not in sources:
        raise BadRequestError("Ese cargo no es una de las opciones de este asiento.")
    await ensure_can_administer(db, user_id, access, seat)
    previous = await current_choice(db, position_id)
    if previous is not None:
        if starts_on <= previous.starts_on:
            raise BadRequestError("El nuevo periodo debe empezar después del vigente.")
        previous.ends_on = starts_on - timedelta(days=1)
        await db.flush()
    choice = DerivedChoice(
        position_id=position_id,
        source_position_type_id=source_position_type_id,
        starts_on=starts_on,
        agreement_ref=agreement_ref,
    )
    db.add(choice)
    await db.commit()
    return choice


async def search_held(db: AsyncSession, geo: GeoScope, term: str, limit: int) -> list[uuid.UUID]:
    """Seats with a current appointment whose position or holder matches `term` (visible
    bodies only)."""
    from app.modules.party_structure.service import visible_filter  # noqa: PLC0415 - cycle
    from app.modules.people.models import Person as Holder  # noqa: PLC0415

    pattern = f"%{term.strip().lower()}%"
    statement = (
        select(col(Position.id))
        .join(PositionType, col(PositionType.id) == col(Position.position_type_id))
        .join(Appointment, col(Appointment.position_id) == col(Position.id))
        .join(Holder, col(Holder.id) == col(Appointment.person_id))
        .join(Body, col(Body.id) == col(Position.body_id))
        .where(
            col(Appointment.ended_on).is_(None),
            col(Appointment.deleted_at).is_(None),
            col(Position.deleted_at).is_(None),
            (func.lower(col(PositionType.name)).like(pattern))
            | (func.f_unaccent(func.lower(col(Holder.search_name))).like(func.f_unaccent(pattern))),
        )
        .order_by(col(PositionType.sort_order))
        .limit(limit)
    )
    visible = visible_filter(geo)
    if visible is not None:
        statement = statement.where(visible)
    return [seat for seat in (await db.execute(statement)).scalars() if seat is not None]
