"""Access to the system from appointments (phase 3, D-104).

- The account belongs to the person, not to the position (`person_accounts`): one per person,
  created invited (D-35) or reused.
- Each appointment with access originates one grant (origin `appointment`, `source_id` = the
  appointment) with the appointment's role and the seat's territory as scope (D-101).
- Accounts that come from a position always require TOTP (`users.mfa_required`, sticky).
- Ending the appointment removes its grant; sessions are revoked only when the account is left
  without grants, since authorization is checked on every request.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.mail import OutgoingEmail
from app.modules.identity import repository as identity_repo
from app.modules.identity.container import IdentityServices
from app.modules.identity.models import GrantOrigin, ScopeLevel, User, UserGrant, UserStatus
from app.modules.identity.services.access import Access
from app.modules.identity.services.credentials import issue_invitation
from app.modules.identity.services.grants import (
    ScopeSpec,
    add_grant,
    ensure_can_hand_out,
    remove_grant,
)
from app.modules.identity.services.sessions import revoke_user_sessions
from app.modules.party_structure import appointments as seats
from app.modules.party_structure import coordinations
from app.modules.party_structure.appointments import Level, Seat
from app.modules.party_structure.models import Appointment, EndReason, PersonAccount
from app.modules.people.models import Person
from app.modules.people.service import full_name


@dataclass(frozen=True, slots=True)
class AccessResult:
    appointment: Appointment
    user: User
    invitation: OutgoingEmail | None  # sent by the caller after the commit


async def seat_scopes(db: AsyncSession, seat: Seat) -> list[ScopeSpec]:
    """The seat's territory as grant scope (D-108): national, circumscription, state or node."""
    if seat.level == Level.NATIONAL and seat.body.state_code is None:
        return [(ScopeLevel.NATIONAL, None)]
    if seat.level == Level.CIRCUMSCRIPTION:
        assert seat.position.region_number is not None  # noqa: S101
        region = await seats.node_of(
            db, "electoral_regions", "region_number", seat.position.region_number
        )
        return [(ScopeLevel.ELECTORAL_REGION, region)]
    if seat.body_type.coordination_kind is not None:
        coordination = await coordinations.coordination_of_seat(db, seat)
        assert coordination is not None  # noqa: S101
        return await coordinations.scopes_of(db, coordination)
    body = seat.body
    for column, level in (
        ("municipality_id", ScopeLevel.MUNICIPALITY),
        ("federal_district_id", ScopeLevel.FEDERAL_DISTRICT),
        ("local_district_id", ScopeLevel.LOCAL_DISTRICT),
    ):
        if getattr(body, column) is not None:
            return [(level, getattr(body, column))]
    assert body.state_code is not None  # noqa: S101 - state bodies keep their code
    return [(ScopeLevel.STATE, await seats.node_of(db, "states", "state_code", body.state_code))]


async def account_of(db: AsyncSession, person_id: uuid.UUID) -> User | None:
    link = (
        await db.execute(
            select(PersonAccount).where(
                col(PersonAccount.person_id) == person_id, col(PersonAccount.deleted_at).is_(None)
            )
        )
    ).scalar_one_or_none()
    return await identity_repo.user_by_id(db, link.user_id) if link else None


async def _account(
    db: AsyncSession,
    services: IdentityServices,
    *,
    actor_id: uuid.UUID,
    person: Person,
    email: str | None,
) -> tuple[User, OutgoingEmail | None]:
    """The person's account, linking or creating one (invited) by e-mail if needed."""
    existing = await account_of(db, pk(person))
    if existing is not None:
        return existing, None
    if not email:
        raise BadRequestError("La persona no tiene cuenta: indica el correo para invitarla.")
    user = await identity_repo.user_by_email(db, email)
    message = None
    if user is not None:
        linked = (
            await db.execute(
                select(PersonAccount).where(
                    col(PersonAccount.user_id) == pk(user), col(PersonAccount.deleted_at).is_(None)
                )
            )
        ).scalar_one_or_none()
        if linked is not None:
            raise ConflictError("Ese correo ya pertenece a la cuenta de otra persona.")
    else:
        user = User(email=email, full_name=full_name(person), status=UserStatus.INVITED)
        db.add(user)
        await db.flush()
        _, message = await issue_invitation(db, services, user, invited_by=actor_id)
    db.add(PersonAccount(person_id=pk(person), user_id=pk(user)))
    await db.flush()
    return user, message


async def _grant_of(db: AsyncSession, appointment_id: uuid.UUID) -> UserGrant | None:
    rows = await db.execute(
        select(UserGrant).where(
            col(UserGrant.origin) == GrantOrigin.APPOINTMENT,
            col(UserGrant.source_id) == appointment_id,
        )
    )
    return rows.scalars().first()


async def grant_access(
    db: AsyncSession,
    services: IdentityServices,
    *,
    actor_id: uuid.UUID,
    actor: Access,
    appointment_id: uuid.UUID,
    email: str | None,
    role_id: uuid.UUID | None,
) -> AccessResult:
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None or appointment.deleted_at is not None:
        raise NotFoundError("Nombramiento no encontrado.")
    if appointment.ended_on is not None:
        raise ConflictError("El nombramiento ya terminó.")
    seat = await seats.load_seat(db, appointment.position_id)
    await seats.ensure_can_administer(db, actor_id, actor, seat)
    if await _grant_of(db, pk(appointment)) is not None:
        raise ConflictError("Este nombramiento ya da acceso.")
    role = await identity_repo.role_by_id(db, role_id or appointment.role_id)  # type: ignore[arg-type]
    if role is None:
        raise BadRequestError("Indica el rol del acceso: el cargo no tiene rol por defecto.")
    scopes = await seat_scopes(db, seat)
    # D-104 point 5: whoever grants it must be able to hand out that role in that territory.
    await ensure_can_hand_out(db, actor_id, actor, role, scopes)
    person = await db.get(Person, appointment.person_id)
    assert person is not None  # noqa: S101 - FK
    user, invitation = await _account(db, services, actor_id=actor_id, person=person, email=email)
    user.mfa_required = True
    await add_grant(
        db,
        user_id=pk(user),
        role=role,
        scopes=scopes,
        origin=GrantOrigin.APPOINTMENT,
        source_id=pk(appointment),
        assigned_by=actor_id,
    )
    appointment.grants_access = True
    appointment.role_id = role.id
    await db.commit()
    return AccessResult(appointment=appointment, user=user, invitation=invitation)


async def revoke_access(db: AsyncSession, appointment: Appointment) -> None:
    """Removes the appointment's grant; closes the sessions only if no grant is left (caller
    commits)."""
    grant = await _grant_of(db, pk(appointment))
    appointment.grants_access = False
    if grant is None:
        return
    user_id = grant.user_id
    await remove_grant(db, grant)
    left = (
        await db.execute(select(col(UserGrant.id)).where(col(UserGrant.user_id) == user_id))
    ).first()
    if left is None:
        await revoke_user_sessions(db, user_id, reason="appointment_ended")


async def expire_due(db: AsyncSession, today: date) -> int:
    """Daily job: ends the appointments whose period is over and revokes their access."""
    due = (
        (
            await db.execute(
                select(Appointment).where(
                    col(Appointment.ended_on).is_(None),
                    col(Appointment.deleted_at).is_(None),
                    col(Appointment.ends_on) < today,
                )
            )
        )
        .scalars()
        .all()
    )
    for appointment in due:
        appointment.ended_on = appointment.ends_on
        appointment.end_reason = EndReason.TERM_END
        appointment.end_notes = "Terminado por vencimiento del periodo."
        seat = await seats.load_seat(db, appointment.position_id)
        seat.position.vacant_since = appointment.ends_on
        await revoke_access(db, appointment)
    await db.commit()
    return len(due)


async def user_of_appointment(db: AsyncSession, appointment_id: uuid.UUID) -> uuid.UUID | None:
    grant = await _grant_of(db, appointment_id)
    return grant.user_id if grant else None


# --- for other modules (Peace Movement credit, D-103) -----------------------------------------


async def current_seats_of_user(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Seats the user's person currently holds."""
    rows = await db.execute(
        select(col(Appointment.position_id))
        .join(PersonAccount, col(PersonAccount.person_id) == col(Appointment.person_id))
        .where(
            col(PersonAccount.user_id) == user_id,
            col(PersonAccount.deleted_at).is_(None),
            col(Appointment.ended_on).is_(None),
            col(Appointment.deleted_at).is_(None),
        )
    )
    return list(rows.scalars())


async def seat_labels(db: AsyncSession, position_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """«Position, territory» of each seat (circumscription number when there is one)."""
    from app.modules.party_structure.service import territory_names  # noqa: PLC0415 - cycle

    labels: dict[uuid.UUID, str] = {}
    seats_ = [await seats.load_seat(db, position_id) for position_id in dict.fromkeys(position_ids)]
    names = await territory_names(db, [seat.body for seat in seats_])
    for seat in seats_:
        region = (
            f" {seat.position.region_number}" if seat.position.region_number is not None else ""
        )
        labels[pk(seat.position)] = f"{seat.position_type.name}{region}, {names[pk(seat.body)]}"
    return labels


async def seat_is_held(db: AsyncSession, position_id: uuid.UUID) -> bool:
    current = await seats.current_appointments(db, [position_id])
    return position_id in current
