"""/party-structure — statutory catalog, bodies, seats and appointments (D-105, D-107, D-108)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, col

from app.core.db.base import pk
from app.core.db.session import SessionDep
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.mail import send_safely
from app.core.pagination import CursorPage, PageParams, page_params
from app.modules.identity.container import IdentityServices, ServicesDep
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm
from app.modules.identity.schemas import RoleSummary
from app.modules.identity.services.scopes import GeoScope
from app.modules.party_structure import access, appointments, service
from app.modules.party_structure.appointments import Seat
from app.modules.party_structure.models import (
    Appointment,
    AppointmentKind,
    Body,
    BodyType,
    CoordinationPositionType,
    EndReason,
    PositionType,
    TerritorialLevel,
)
from app.modules.party_structure.permissions import StructurePerm
from app.modules.party_structure.schemas import (
    AccessIn,
    AppointmentEndIn,
    AppointmentIn,
    AppointmentOut,
    AppointmentUpdate,
    BodyDissolveIn,
    BodyInstallIn,
    BodyOut,
    BodyTypeIn,
    BodyTypeOut,
    BodyTypeRef,
    BodyTypeUpdate,
    CoordinationPositionTypeIn,
    CoordinationPositionTypeOut,
    DerivedChoiceIn,
    IncompatibilityIn,
    IncompatibilityOut,
    PersonAppointmentOut,
    PositionTypeIn,
    PositionTypeOut,
    PositionTypeRef,
    PositionTypeUpdate,
    SeatOut,
)
from app.modules.people.models import Person
from app.modules.people.views import CryptoDep, person_summary

router = APIRouter(prefix="/party-structure", tags=["party-structure"])

CatalogManager = Annotated[CurrentUser, permission(StructurePerm.CATALOG_MANAGE)]
BodyReader = Annotated[CurrentUser, permission(StructurePerm.BODY_READ)]
BodyWriter = Annotated[CurrentUser, permission(StructurePerm.BODY_WRITE)]
BodyId = Annotated[uuid.UUID, "Id del órgano"]


# --- catalog ----------------------------------------------------------------------------------


def _fields(row: SQLModel, schema: type[BaseModel]) -> dict[str, Any]:
    """The row's columns that the output schema declares (schemas forbid extra fields)."""
    return {name: getattr(row, name) for name in schema.model_fields if hasattr(row, name)}


def _position_out(
    position: PositionType,
    sources: list[PositionType],
    role: RoleSummary | None,
) -> PositionTypeOut:
    return PositionTypeOut.model_validate(
        {
            **_fields(position, PositionTypeOut),
            "default_role": role,
            "derived_from": [PositionTypeRef.model_validate(s) for s in sources],
        }
    )


@router.get("/catalog", operation_id="getStructureCatalog", summary="Órganos y cargos del estatuto")
async def get_catalog(db: SessionDep, _: BodyReader) -> list[BodyTypeOut]:
    bodies, positions, derivations, roles = await service.catalog(db)
    by_id = {pk(p): p for p in positions}
    out = []
    for body_type in bodies:
        items = [
            _position_out(
                p,
                [by_id[s] for s in derivations.get(pk(p), []) if s in by_id],
                RoleSummary.model_validate(roles[p.default_role_id])
                if p.default_role_id in roles
                else None,
            )
            for p in positions
            if p.body_type_id == body_type.id
        ]
        out.append(
            BodyTypeOut.model_validate({**_fields(body_type, BodyTypeOut), "positions": items})
        )
    return out


@router.post(
    "/body-types",
    operation_id="createBodyType",
    summary="Agregar un tipo de órgano",
    status_code=status.HTTP_201_CREATED,
)
async def create_body_type(db: SessionDep, _: CatalogManager, body: BodyTypeIn) -> BodyTypeOut:
    created = await service.create_body_type(db, body)
    return BodyTypeOut.model_validate({**_fields(created, BodyTypeOut), "positions": []})


@router.patch(
    "/body-types/{body_type_id}", operation_id="updateBodyType", summary="Editar un tipo de órgano"
)
async def update_body_type(
    db: SessionDep, _: CatalogManager, body_type_id: uuid.UUID, body: BodyTypeUpdate
) -> BodyTypeRef:
    return BodyTypeRef.model_validate(await service.update_body_type(db, body_type_id, body))


async def _one_position(db: AsyncSession, position: PositionType) -> PositionTypeOut:
    sources = await service.positions_by_id(db, await service.derived_sources(db, pk(position)))
    roles = await service.roles_by_id(
        db, {position.default_role_id} if position.default_role_id else set()
    )
    role = roles.get(position.default_role_id) if position.default_role_id else None
    return _position_out(
        position, list(sources.values()), RoleSummary.model_validate(role) if role else None
    )


@router.post(
    "/position-types",
    operation_id="createPositionType",
    summary="Agregar un cargo (sin migraciones)",
    status_code=status.HTTP_201_CREATED,
)
async def create_position_type(
    db: SessionDep, user: CatalogManager, body: PositionTypeIn
) -> PositionTypeOut:
    return await _one_position(db, await service.create_position_type(db, user.access, body))


@router.patch(
    "/position-types/{position_type_id}",
    operation_id="updatePositionType",
    summary="Editar un cargo",
)
async def update_position_type(
    db: SessionDep, user: CatalogManager, position_type_id: uuid.UUID, body: PositionTypeUpdate
) -> PositionTypeOut:
    position = await service.update_position_type(db, user.access, position_type_id, body)
    return await _one_position(db, position)


@router.get(
    "/incompatibilities",
    operation_id="listIncompatibilities",
    summary="Pares de cargos incompatibles",
)
async def list_incompatibilities(db: SessionDep, _: BodyReader) -> list[IncompatibilityOut]:
    rows = await service.incompatibilities(db)
    positions = await service.positions_by_id(
        db, list({r.position_type_a_id for r in rows} | {r.position_type_b_id for r in rows})
    )
    return [
        IncompatibilityOut(
            id=pk(r),
            position_type_a=PositionTypeRef.model_validate(positions[r.position_type_a_id]),
            position_type_b=PositionTypeRef.model_validate(positions[r.position_type_b_id]),
            notes=r.notes,
        )
        for r in rows
    ]


@router.post(
    "/incompatibilities",
    operation_id="addIncompatibility",
    summary="Registrar dos cargos incompatibles",
    status_code=status.HTTP_201_CREATED,
)
async def add_incompatibility(
    db: SessionDep, _: CatalogManager, body: IncompatibilityIn
) -> IncompatibilityOut:
    row = await service.add_incompatibility(db, body)
    positions = await service.positions_by_id(db, [row.position_type_a_id, row.position_type_b_id])
    return IncompatibilityOut(
        id=pk(row),
        position_type_a=PositionTypeRef.model_validate(positions[row.position_type_a_id]),
        position_type_b=PositionTypeRef.model_validate(positions[row.position_type_b_id]),
        notes=row.notes,
    )


@router.delete(
    "/incompatibilities/{incompatibility_id}",
    operation_id="removeIncompatibility",
    summary="Quitar una incompatibilidad",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_incompatibility(
    db: SessionDep, _: CatalogManager, incompatibility_id: uuid.UUID
) -> None:
    await service.remove_incompatibility(db, incompatibility_id)


async def _coordination_out(
    db: AsyncSession, rows: list[CoordinationPositionType]
) -> list[CoordinationPositionTypeOut]:
    roles = await service.roles_by_id(db, {r.default_role_id for r in rows if r.default_role_id})
    return [
        CoordinationPositionTypeOut.model_validate(
            {
                **_fields(r, CoordinationPositionTypeOut),
                "default_role": RoleSummary.model_validate(roles[r.default_role_id])
                if r.default_role_id in roles
                else None,
            }
        )
        for r in rows
    ]


@router.get(
    "/coordination-position-types",
    operation_id="listCoordinationPositionTypes",
    summary="Cargos del equipo de las coordinaciones territoriales",
)
async def list_coordination_position_types(
    db: SessionDep, _: BodyReader
) -> list[CoordinationPositionTypeOut]:
    return await _coordination_out(db, await service.coordination_position_types(db))


@router.post(
    "/coordination-position-types",
    operation_id="createCoordinationPositionType",
    summary="Agregar un cargo de coordinación",
    status_code=status.HTTP_201_CREATED,
)
async def create_coordination_position_type(
    db: SessionDep, user: CatalogManager, body: CoordinationPositionTypeIn
) -> CoordinationPositionTypeOut:
    row = await service.create_coordination_position_type(db, user.access, body)
    [out] = await _coordination_out(db, [row])
    return out


# --- bodies -----------------------------------------------------------------------------------


async def _bodies_out(db: AsyncSession, bodies: list[Body]) -> list[BodyOut]:
    names = await service.territory_names(db, bodies)
    types = {
        pk(t): t for t in [await db.get(BodyType, i) for i in {b.body_type_id for b in bodies}] if t
    }
    return [
        BodyOut.model_validate(
            {
                **_fields(b, BodyOut),
                "body_type": BodyTypeRef.model_validate(types[b.body_type_id]),
                "territory": names[pk(b)],
                "status": "dissolved" if b.dissolved_on else "installed",
            }
        )
        for b in bodies
    ]


@router.get("/bodies", operation_id="listBodies", summary="Órganos instalados en tu alcance")
async def list_bodies(
    db: SessionDep,
    user: BodyReader,
    params: Annotated[PageParams, Depends(page_params)],
    level: TerritorialLevel | None = None,
    body_type_id: uuid.UUID | None = None,
    state_code: Annotated[int | None, Query(ge=1, le=32)] = None,
    include_dissolved: bool = False,
) -> CursorPage[BodyOut]:
    page = await service.list_bodies(
        db,
        user.geo,
        params,
        level=level,
        body_type_id=body_type_id,
        state_code=state_code,
        include_dissolved=include_dissolved,
    )
    return CursorPage[BodyOut](
        items=await _bodies_out(db, page.items),
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/bodies/{body_id}", operation_id="getBody", summary="Detalle de un órgano")
async def get_body(db: SessionDep, user: BodyReader, body_id: uuid.UUID) -> BodyOut:
    [out] = await _bodies_out(db, [await service.visible_body(db, user.geo, body_id)])
    return out


@router.post(
    "/bodies",
    operation_id="installBody",
    summary="Registrar la instalación de un comité distrital o municipal",
    status_code=status.HTTP_201_CREATED,
)
async def install_body(db: SessionDep, user: BodyWriter, body: BodyInstallIn) -> BodyOut:
    [out] = await _bodies_out(db, [await service.install_body(db, user.geo, body)])
    return out


@router.post(
    "/bodies/{body_id}/dissolve",
    operation_id="dissolveBody",
    summary="Registrar la disolución de un comité distrital o municipal",
)
async def dissolve_body(
    db: SessionDep, user: BodyWriter, body_id: uuid.UUID, body: BodyDissolveIn
) -> BodyOut:
    [out] = await _bodies_out(db, [await service.dissolve_body(db, user.geo, body_id, body)])
    return out


# --- seats and appointments (phase 2) ---------------------------------------------------------

AppointmentReader = Annotated[CurrentUser, permission(StructurePerm.APPOINTMENT_READ)]
AppointmentWriter = Annotated[CurrentUser, permission(StructurePerm.APPOINTMENT_WRITE)]


async def _persons(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Person]:
    if not ids:
        return {}
    rows = await db.execute(select(Person).where(col(Person.id).in_(ids)))
    return {pk(p): p for p in rows.scalars()}


async def _appointments_out(
    db: AsyncSession, crypto: CryptoDep, user: CurrentUser, rows: list[Appointment]
) -> list[AppointmentOut]:
    persons = await _persons(db, {r.person_id for r in rows})
    accounts = {r.id: await access.user_of_appointment(db, pk(r)) for r in rows}
    roles = await service.roles_by_id(db, {r.role_id for r in rows if r.role_id})
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    return [
        AppointmentOut.model_validate(
            {
                **_fields(r, AppointmentOut),
                "person": person_summary(crypto, persons[r.person_id], sensitive),
                "role": RoleSummary.model_validate(roles[r.role_id])
                if r.role_id in roles
                else None,
                "current": r.ended_on is None,
                "has_access": accounts[r.id] is not None,
                "user_id": accounts[r.id],
            }
        )
        for r in rows
    ]


async def _visible_seat(db: AsyncSession, geo: GeoScope, position_id: uuid.UUID) -> Seat:
    seat = await appointments.load_seat(db, position_id)
    await service.visible_body(db, geo, pk(seat.body))
    return seat


@router.get(
    "/bodies/{body_id}/positions",
    operation_id="listBodyPositions",
    summary="Asientos de un órgano con su titular vigente",
)
async def list_positions(
    db: SessionDep, crypto: CryptoDep, user: AppointmentReader, body_id: uuid.UUID
) -> list[SeatOut]:
    body = await service.visible_body(db, user.geo, body_id)
    seats = await appointments.seats_of(db, pk(body))
    current = await appointments.current_appointments(db, [pk(s.position) for s in seats])
    current_out = {
        a.position_id: a for a in await _appointments_out(db, crypto, user, list(current.values()))
    }
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    out = []
    for seat in seats:
        source_ref, holder, pending = None, None, False
        if seat.position_type.is_derived:
            source, appointment = await appointments.derived_holder(db, seat)
            pending = source is None
            if source is not None:
                source_ref = PositionTypeRef.model_validate(
                    (await service.positions_by_id(db, [source]))[source]
                )
            if appointment is not None:
                person = (await _persons(db, {appointment.person_id}))[appointment.person_id]
                holder = person_summary(crypto, person, sensitive)
        out.append(
            SeatOut(
                id=pk(seat.position),
                body_id=pk(body),
                position_type=PositionTypeRef.model_validate(seat.position_type),
                region_number=seat.position.region_number,
                is_derived=seat.position_type.is_derived,
                vacant_since=seat.position.vacant_since,
                current=current_out.get(pk(seat.position)),
                derived_from=source_ref,
                derived_holder=holder,
                choice_pending=pending,
            )
        )
    return out


@router.get(
    "/positions/{position_id}/appointments",
    operation_id="listPositionAppointments",
    summary="Historial de nombramientos de un asiento",
)
async def list_position_appointments(
    db: SessionDep, crypto: CryptoDep, user: AppointmentReader, position_id: uuid.UUID
) -> list[AppointmentOut]:
    seat = await _visible_seat(db, user.geo, position_id)
    return await _appointments_out(
        db, crypto, user, await appointments.history(db, pk(seat.position))
    )


@router.post(
    "/positions/{position_id}/appointments",
    operation_id="appoint",
    summary="Nombrar al titular de un asiento",
    description=(
        "El asiento debe estar vacante y no ser derivado. El titular es una persona con CURP. "
        "Se rechazan los cargos incompatibles y los periodos consecutivos de más (409). Solo se "
        "nombra en cargos de nivel inferior al propio y dentro del alcance (D-105, D-108)."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def appoint(
    db: SessionDep,
    crypto: CryptoDep,
    services: ServicesDep,
    background: BackgroundTasks,
    user: AppointmentWriter,
    position_id: uuid.UUID,
    body: AppointmentIn,
) -> AppointmentOut:
    created = await appointments.appoint(
        db,
        user_id=user.id,
        access=user.access,
        position_id=position_id,
        person_id=body.person_id,
        kind=AppointmentKind(body.kind),
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        appointed_by=body.appointed_by,
        agreement_ref=body.agreement_ref,
    )
    pending = None
    created_id = pk(created)
    if body.access is not None:
        pending = await _try_access(db, services, background, user, created_id, body.access)
    # Reloaded: a refused access rolls back the session, which expires loaded objects.
    reloaded = await db.get(Appointment, created_id, populate_existing=True)
    assert reloaded is not None  # noqa: S101 - committed above
    [out] = await _appointments_out(db, crypto, user, [reloaded])
    return out.model_copy(update={"access_pending": pending})


async def _try_access(
    db: AsyncSession,
    services: IdentityServices,
    background: BackgroundTasks,
    user: CurrentUser,
    appointment_id: uuid.UUID,
    body: AccessIn,
) -> str | None:
    """D-104 point 5: the appointment stands even if its author cannot grant the access."""
    if not user.has(StructurePerm.APPOINTMENT_GRANT_ACCESS):
        return "Sin permiso para dar acceso: lo debe otorgar quien tenga ese permiso."
    try:
        result = await access.grant_access(
            db,
            services,
            actor_id=user.id,
            actor=user.access,
            appointment_id=appointment_id,
            email=body.email,
            role_id=body.role_id,
        )
    except (ForbiddenError, BadRequestError, ConflictError) as error:
        await db.rollback()
        return error.detail
    if result.invitation is not None:
        background.add_task(send_safely, services.mailer, result.invitation)
    return None


@router.patch(
    "/appointments/{appointment_id}",
    operation_id="updateAppointment",
    summary="Corregir periodo o acuerdo de un nombramiento",
)
async def update_appointment(
    db: SessionDep,
    crypto: CryptoDep,
    user: AppointmentWriter,
    appointment_id: uuid.UUID,
    body: AppointmentUpdate,
) -> AppointmentOut:
    updated = await appointments.update_appointment(
        db,
        user_id=user.id,
        access=user.access,
        appointment_id=appointment_id,
        ends_on=body.ends_on,
        appointed_by=body.appointed_by,
        agreement_ref=body.agreement_ref,
    )
    [out] = await _appointments_out(db, crypto, user, [updated])
    return out


@router.post(
    "/appointments/{appointment_id}/end",
    operation_id="endAppointment",
    summary="Terminar un nombramiento (el asiento queda vacante)",
)
async def end_appointment(
    db: SessionDep,
    crypto: CryptoDep,
    user: AppointmentWriter,
    appointment_id: uuid.UUID,
    body: AppointmentEndIn,
) -> AppointmentOut:
    ended = await appointments.end_appointment(
        db,
        user_id=user.id,
        access=user.access,
        appointment_id=appointment_id,
        ended_on=body.ended_on,
        reason=EndReason(body.reason),
        notes=body.notes,
    )
    [out] = await _appointments_out(db, crypto, user, [ended])
    return out


@router.post(
    "/positions/{position_id}/derived-choice",
    operation_id="chooseDerivedSource",
    summary="Elegir de qué cargo toma su titular un asiento derivado en este periodo",
)
async def choose_derived_source(
    db: SessionDep, user: AppointmentWriter, position_id: uuid.UUID, body: DerivedChoiceIn
) -> PositionTypeRef:
    choice = await appointments.choose_source(
        db,
        user_id=user.id,
        access=user.access,
        position_id=position_id,
        source_position_type_id=body.source_position_type_id,
        starts_on=body.starts_on,
        agreement_ref=body.agreement_ref,
    )
    positions = await service.positions_by_id(db, [choice.source_position_type_id])
    return PositionTypeRef.model_validate(positions[choice.source_position_type_id])


@router.get(
    "/people/{person_id}/appointments",
    operation_id="listPersonAppointments",
    summary="Cargos de una persona (en órganos visibles)",
)
async def list_person_appointments(
    db: SessionDep,
    crypto: CryptoDep,
    user: AppointmentReader,
    person_id: uuid.UUID,
    current_only: bool = True,
) -> list[PersonAppointmentOut]:
    rows = await appointments.appointments_of_person(db, person_id, current_only=current_only)
    seats = {r.id: await appointments.load_seat(db, r.position_id) for r in rows}
    visible = {
        pk(b)
        for b in await service.visible_bodies(db, user.geo, {pk(s.body) for s in seats.values()})
    }
    rows = [r for r in rows if pk(seats[r.id].body) in visible]
    names = await service.territory_names(db, [seats[r.id].body for r in rows])
    base = await _appointments_out(db, crypto, user, rows)
    return [
        PersonAppointmentOut(
            **out.model_dump(),
            position_type=PositionTypeRef.model_validate(seats[r.id].position_type),
            body=BodyTypeRef.model_validate(seats[r.id].body_type),
            body_id=pk(seats[r.id].body),
            territory=names[pk(seats[r.id].body)],
        )
        for r, out in zip(rows, base, strict=True)
    ]


AccessGranter = Annotated[CurrentUser, permission(StructurePerm.APPOINTMENT_GRANT_ACCESS)]


@router.post(
    "/appointments/{appointment_id}/access",
    operation_id="grantAppointmentAccess",
    summary="Dar acceso al sistema al titular (invitación y TOTP obligatorio)",
)
async def grant_appointment_access(
    db: SessionDep,
    crypto: CryptoDep,
    services: ServicesDep,
    background: BackgroundTasks,
    user: AccessGranter,
    appointment_id: uuid.UUID,
    body: AccessIn,
) -> AppointmentOut:
    result = await access.grant_access(
        db,
        services,
        actor_id=user.id,
        actor=user.access,
        appointment_id=appointment_id,
        email=body.email,
        role_id=body.role_id,
    )
    if result.invitation is not None:
        background.add_task(send_safely, services.mailer, result.invitation)
    [out] = await _appointments_out(db, crypto, user, [result.appointment])
    return out


@router.delete(
    "/appointments/{appointment_id}/access",
    operation_id="revokeAppointmentAccess",
    summary="Quitar el acceso que da un nombramiento (sigue vigente el cargo)",
)
async def revoke_appointment_access(
    db: SessionDep, crypto: CryptoDep, user: AccessGranter, appointment_id: uuid.UUID
) -> AppointmentOut:
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None or appointment.deleted_at is not None:
        raise NotFoundError("Nombramiento no encontrado.")
    seat = await appointments.load_seat(db, appointment.position_id)
    await appointments.ensure_can_administer(db, user.id, user.access, seat)
    await access.revoke_access(db, appointment)
    await db.commit()
    [out] = await _appointments_out(db, crypto, user, [appointment])
    return out
