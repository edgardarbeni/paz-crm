"""Territorial coordinations (phase 4, D-110).

A coordination is a body of one of the three coordination body types: federal (federal districts
of any states), local (local districts of one state) or sectional (sections of one state). Its
seats and appointments are the ordinary ones (D-108, D-109); its territory lives in
`coordination_*` with `added_on` / `removed_on`, and a node belongs to at most one current
coordination of its kind. Coordinations are independent of each other: no hierarchy.

Changing the territory recomputes the grants of its holders (D-101). Only the national level
administers a federal coordination that spans several states.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from http import HTTPStatus
from typing import Any

from sqlalchemy import select, text, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import AppError, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.modules.identity.models import GrantOrigin, ScopeLevel, UserGrant
from app.modules.identity.services.access import Access
from app.modules.identity.services.grants import ScopeSpec, sync_scopes
from app.modules.identity.services.scopes import GeoScope, active_framework
from app.modules.party_structure import appointments as seats
from app.modules.party_structure.models import (
    Appointment,
    Body,
    BodyType,
    CoordinationFederalDistrict,
    CoordinationKind,
    CoordinationLocalDistrict,
    CoordinationSection,
    Position,
)
from app.modules.party_structure.permissions import StructurePerm


class UnprocessableError(AppError):
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "unprocessable"
    title = "La solicitud no cumple las reglas"


@dataclass(frozen=True, slots=True)
class KindSpec:
    model: Any
    column: str
    table: str  # geography table of the nodes
    scope_level: ScopeLevel
    label: str
    # SQL over geography.sections `s` that ties a section to a node `:node`/`n.id`.
    section_link: str


KINDS: dict[CoordinationKind, KindSpec] = {
    CoordinationKind.FEDERAL: KindSpec(
        CoordinationFederalDistrict,
        "federal_district_id",
        "federal_districts",
        ScopeLevel.FEDERAL_DISTRICT,
        "'Distrito federal ' || n.district_number",
        "s.federal_district_id",
    ),
    CoordinationKind.LOCAL: KindSpec(
        CoordinationLocalDistrict,
        "local_district_id",
        "local_districts",
        ScopeLevel.LOCAL_DISTRICT,
        "'Distrito local ' || n.district_number",
        "s.local_district_id",
    ),
    CoordinationKind.SECTIONAL: KindSpec(
        CoordinationSection,
        "section_id",
        "sections",
        ScopeLevel.SECTION,
        "'Sección ' || n.section_number",
        "s.id",
    ),
}


@dataclass(frozen=True, slots=True)
class Coordination:
    body: Body
    body_type: BodyType
    kind: CoordinationKind


async def body_type_of(db: AsyncSession, kind: CoordinationKind) -> BodyType:
    found = (
        await db.execute(
            select(BodyType).where(
                col(BodyType.coordination_kind) == kind, col(BodyType.deleted_at).is_(None)
            )
        )
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("No existe el tipo de coordinación.")
    return found


async def load(db: AsyncSession, coordination_id: uuid.UUID) -> Coordination:
    row = (
        await db.execute(
            select(Body, BodyType)
            .join(BodyType, col(BodyType.id) == col(Body.body_type_id))
            .where(
                col(Body.id) == coordination_id,
                col(Body.deleted_at).is_(None),
                col(BodyType.coordination_kind).is_not(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Coordinación no encontrada.")
    body, body_type = row
    assert body_type.coordination_kind is not None  # noqa: S101 - filtered above
    return Coordination(body, body_type, CoordinationKind(body_type.coordination_kind))


async def current_nodes(db: AsyncSession, coordination: Coordination) -> list[uuid.UUID]:
    spec = KINDS[coordination.kind]
    rows = await db.execute(
        select(getattr(spec.model, spec.column)).where(
            spec.model.coordination_id == pk(coordination.body),
            spec.model.removed_on.is_(None),
            spec.model.deleted_at.is_(None),
        )
    )
    return list(rows.scalars())


async def territory(db: AsyncSession, coordination: Coordination) -> list[tuple[uuid.UUID, str]]:
    spec = KINDS[coordination.kind]
    nodes = await current_nodes(db, coordination)
    if not nodes:
        return []
    rows = await db.execute(
        text(
            f"SELECT n.id, {spec.label} || ', ' || st.name FROM geography.{spec.table} n "  # noqa: S608
            "JOIN geography.states st ON st.id = n.state_id WHERE n.id = ANY(:ids) "
            "ORDER BY 2"
        ),
        {"ids": nodes},
    )
    return [(node, label) for node, label in rows.all()]


async def _states_of(
    db: AsyncSession, kind: CoordinationKind, node_ids: list[uuid.UUID]
) -> set[int]:
    """The nodes exist and are active in the active framework; returns their states."""
    spec = KINDS[kind]
    framework_id = await active_framework(db)
    rows = (
        await db.execute(
            text(
                f"SELECT n.id, st.state_code FROM geography.{spec.table} n "  # noqa: S608
                "JOIN geography.states st ON st.id = n.state_id "
                "WHERE n.id = ANY(:ids) AND n.framework_id = :fw AND n.is_active"
            ),
            {"ids": node_ids, "fw": framework_id},
        )
    ).all()
    if len(rows) != len(set(node_ids)):
        raise BadRequestError("Algún territorio no existe en el marco geográfico activo.")
    return {int(code) for _, code in rows}


def _ensure_one_state(kind: CoordinationKind, states: set[int]) -> None:
    if kind != CoordinationKind.FEDERAL and len(states) > 1:
        raise UnprocessableError("Una coordinación local o seccional abarca un solo estado.")


async def _ensure_free(
    db: AsyncSession, kind: CoordinationKind, node_ids: list[uuid.UUID], own: uuid.UUID | None
) -> None:
    spec = KINDS[kind]
    taken = (
        await db.execute(
            select(spec.model).where(
                getattr(spec.model, spec.column).in_(node_ids),
                spec.model.removed_on.is_(None),
                spec.model.deleted_at.is_(None),
                spec.model.coordination_id != own if own else true(),
            )
        )
    ).first()
    if taken is not None:
        raise ConflictError(
            "Algún territorio ya pertenece a otra coordinación vigente del mismo tipo."
        )


async def nodes_within(
    db: AsyncSession, geo: GeoScope, kind: CoordinationKind, node_ids: list[uuid.UUID]
) -> bool:
    """Every section of the nodes is inside `geo`."""
    if geo.unrestricted:
        return True
    if not node_ids or not geo.grant_ids:
        return not node_ids
    spec = KINDS[kind]
    outside = (
        await db.execute(
            text(
                f"SELECT 1 FROM geography.sections s WHERE {spec.section_link} = ANY(:ids) "  # noqa: S608
                f"AND s.is_active AND NOT {geo.section_sql('s.id')} LIMIT 1"
            ),
            {"ids": node_ids, **geo.sql_params},
        )
    ).first()
    return outside is None


async def ensure_can_manage(  # noqa: PLR0917
    db: AsyncSession,
    user_id: uuid.UUID,
    access: Access,
    kind: CoordinationKind,
    states: set[int],
    node_ids: list[uuid.UUID],
) -> None:
    """D-105: a grant above the coordinations' level whose scope holds the whole territory; a
    federal coordination across states needs the national level."""
    if access.grants_all:
        return
    for grant in access.grants_for(StructurePerm.COORDINATION_WRITE):
        if await seats.grant_level(db, grant) <= seats.Level.COORDINATION:
            continue
        geo = GeoScope(user_id=user_id, unrestricted=grant.national, grant_ids=(grant.id,))
        if len(states) > 1 and not geo.unrestricted:
            continue
        if await nodes_within(db, geo, kind, node_ids):
            return
    if len(states) > 1:
        raise ForbiddenError("Solo el nivel nacional administra coordinaciones de varios estados.")
    raise ForbiddenError("La coordinación está fuera de tu alcance o de tu nivel.")


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    kind: CoordinationKind,
    name: str,
    node_ids: list[uuid.UUID],
    created_on: date,
    agreement: str | None,
) -> Body:
    nodes = list(dict.fromkeys(node_ids))
    if not nodes:
        raise BadRequestError("Una coordinación necesita territorio.")
    states = await _states_of(db, kind, nodes)
    _ensure_one_state(kind, states)
    await ensure_can_manage(db, user_id, access, kind, states, nodes)
    await _ensure_free(db, kind, nodes, None)
    body_type = await body_type_of(db, kind)
    coordination = Body(
        body_type_id=pk(body_type),
        name=name,
        state_code=next(iter(states)) if len(states) == 1 else None,
        framework_id=await active_framework(db),
        installed_on=created_on,
        installation_agreement=agreement,
    )
    db.add(coordination)
    await db.flush()
    spec = KINDS[kind]
    for node in nodes:
        db.add(
            spec.model(coordination_id=pk(coordination), added_on=created_on, **{spec.column: node})
        )
    await _flush_free(db)
    await seats.ensure_seats(db, coordination)
    await db.commit()
    return coordination


async def _flush_free(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as error:  # a concurrent change took a node
        await db.rollback()
        raise ConflictError(
            "Algún territorio ya pertenece a otra coordinación vigente del mismo tipo."
        ) from error


async def set_territory(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    coordination_id: uuid.UUID,
    node_ids: list[uuid.UUID],
    on: date,
) -> Coordination:
    coordination = await load(db, coordination_id)
    if coordination.body.dissolved_on is not None:
        raise ConflictError("La coordinación está cerrada.")
    wanted = list(dict.fromkeys(node_ids))
    if not wanted:
        raise BadRequestError("Una coordinación necesita territorio; para quitarlo, ciérrala.")
    current = await current_nodes(db, coordination)
    states = await _states_of(db, coordination.kind, wanted)
    _ensure_one_state(coordination.kind, states)
    every = list(dict.fromkeys([*current, *wanted]))
    await ensure_can_manage(
        db,
        user_id,
        access,
        coordination.kind,
        await _states_of(db, coordination.kind, every),
        every,
    )
    added = [node for node in wanted if node not in current]
    removed = [node for node in current if node not in wanted]
    await _ensure_free(db, coordination.kind, added, pk(coordination.body))
    spec = KINDS[coordination.kind]
    if removed:
        rows = await db.execute(
            select(spec.model).where(
                spec.model.coordination_id == pk(coordination.body),
                getattr(spec.model, spec.column).in_(removed),
                spec.model.removed_on.is_(None),
            )
        )
        for row in rows.scalars():
            row.removed_on = on
    for node in added:
        db.add(
            spec.model(coordination_id=pk(coordination.body), added_on=on, **{spec.column: node})
        )
    coordination.body.state_code = next(iter(states)) if len(states) == 1 else None
    await _flush_free(db)
    await sync_holders(db, coordination)
    await db.commit()
    return coordination


async def scopes_of(db: AsyncSession, coordination: Coordination) -> list[ScopeSpec]:
    level = KINDS[coordination.kind].scope_level
    return [(level, node) for node in await current_nodes(db, coordination)]


async def sync_holders(db: AsyncSession, coordination: Coordination) -> int:
    """The grants of the coordination's current holders follow its territory (caller commits)."""
    scopes = await scopes_of(db, coordination)
    grants = (
        (
            await db.execute(
                select(UserGrant)
                .join(Appointment, col(Appointment.id) == col(UserGrant.source_id))
                .join(Position, col(Position.id) == col(Appointment.position_id))
                .where(
                    col(UserGrant.origin) == GrantOrigin.APPOINTMENT,
                    col(Position.body_id) == pk(coordination.body),
                    col(Appointment.ended_on).is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for grant in grants:
        await sync_scopes(db, grant, scopes)
    return len(grants)


async def close(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    coordination_id: uuid.UUID,
    closed_on: date,
    agreement: str | None,
) -> Coordination:
    coordination = await load(db, coordination_id)
    if coordination.body.dissolved_on is not None:
        raise ConflictError("La coordinación ya está cerrada.")
    nodes = await current_nodes(db, coordination)
    await ensure_can_manage(
        db,
        user_id,
        access,
        coordination.kind,
        await _states_of(db, coordination.kind, nodes),
        nodes,
    )
    busy = (
        await db.execute(
            select(col(Appointment.id))
            .join(Position, col(Position.id) == col(Appointment.position_id))
            .where(
                col(Position.body_id) == pk(coordination.body),
                col(Appointment.ended_on).is_(None),
                col(Appointment.deleted_at).is_(None),
            )
        )
    ).first()
    if busy is not None:
        raise ConflictError("Termina primero los nombramientos vigentes de la coordinación.")
    if coordination.body.installed_on and closed_on < coordination.body.installed_on:
        raise BadRequestError("El cierre no puede ser anterior a la creación.")
    spec = KINDS[coordination.kind]
    rows = await db.execute(
        select(spec.model).where(
            spec.model.coordination_id == pk(coordination.body), spec.model.removed_on.is_(None)
        )
    )
    for row in rows.scalars():
        row.removed_on = closed_on  # frees the territory for other coordinations
    coordination.body.dissolved_on = closed_on
    coordination.body.dissolution_agreement = agreement
    await db.commit()
    return coordination


async def coordination_of_seat(db: AsyncSession, seat: seats.Seat) -> Coordination | None:
    if seat.body_type.coordination_kind is None:
        return None
    return Coordination(
        seat.body, seat.body_type, CoordinationKind(seat.body_type.coordination_kind)
    )
