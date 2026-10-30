"""Party structure, phase 1: the statutory catalog and the installed bodies (D-105, D-107).

Visibility of a body (query layer, D-34/D-101): national bodies are visible to whoever holds the
read permission; a state body when its state touches the scope; a district or municipal body
when its node does. Writes (installation, dissolution) need the node inside the scope.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.identity import repository as identity_repo
from app.modules.identity.models import Role, ScopeLevel
from app.modules.identity.services.access import Access, ensure_can_assign
from app.modules.identity.services.scopes import (
    GeoScope,
    active_framework,
    ensure_node_within,
)
from app.modules.party_structure.models import (
    Body,
    BodyType,
    CoordinationKind,
    CoordinationPositionType,
    DistrictKind,
    PositionDerivation,
    PositionIncompatibility,
    PositionType,
    TerritorialLevel,
)
from app.modules.party_structure.schemas import (
    BodyDissolveIn,
    BodyInstallIn,
    BodyTypeIn,
    BodyTypeUpdate,
    CoordinationPositionTypeIn,
    IncompatibilityIn,
    PositionTypeIn,
    PositionTypeUpdate,
)


def _alive(model: Any) -> ColumnElement[bool]:
    return col(model.deleted_at).is_(None)


async def _flush_unique(db: AsyncSession, what: str) -> None:
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise ConflictError(f"Ya existe {what} con esa clave.") from error


# --- catalog ----------------------------------------------------------------------------------


async def roles_by_id(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Role]:
    roles = await identity_repo.roles_by_ids(db, list(ids))
    return {pk(role): role for role in roles}


async def catalog(
    db: AsyncSession,
) -> tuple[
    list[BodyType], list[PositionType], dict[uuid.UUID, list[uuid.UUID]], dict[uuid.UUID, Role]
]:
    bodies = list(
        (
            await db.execute(
                select(BodyType)
                .where(_alive(BodyType))
                .order_by(col(BodyType.sort_order), col(BodyType.name))
            )
        ).scalars()
    )
    positions = list(
        (
            await db.execute(
                select(PositionType)
                .where(_alive(PositionType))
                .order_by(col(PositionType.sort_order), col(PositionType.name))
            )
        ).scalars()
    )
    derivations: dict[uuid.UUID, list[uuid.UUID]] = {}
    for row in (
        await db.execute(select(PositionDerivation).where(_alive(PositionDerivation)))
    ).scalars():
        derivations.setdefault(row.position_type_id, []).append(row.source_position_type_id)
    roles = await roles_by_id(db, {p.default_role_id for p in positions if p.default_role_id})
    return bodies, positions, derivations, roles


async def _body_type(db: AsyncSession, body_type_id: uuid.UUID) -> BodyType:
    found = await db.get(BodyType, body_type_id)
    if found is None or found.deleted_at is not None:
        raise NotFoundError("Tipo de órgano no encontrado.")
    return found


async def _position_type(db: AsyncSession, position_type_id: uuid.UUID) -> PositionType:
    found = await db.get(PositionType, position_type_id)
    if found is None or found.deleted_at is not None:
        raise NotFoundError("Cargo no encontrado.")
    return found


async def _default_role(
    db: AsyncSession, actor: Access, role_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Only roles the actor could hand out may be a position's default (D-52, D-104)."""
    if role_id is None:
        return None
    role = await identity_repo.role_by_id(db, role_id)
    if role is None:
        raise BadRequestError("El rol por defecto no existe.")
    await ensure_can_assign(db, actor, [role])
    return role_id


async def create_body_type(db: AsyncSession, body: BodyTypeIn) -> BodyType:
    body_type = BodyType(**body.model_dump())
    db.add(body_type)
    await _flush_unique(db, "un tipo de órgano")
    await db.commit()
    return body_type


async def update_body_type(
    db: AsyncSession, body_type_id: uuid.UUID, body: BodyTypeUpdate
) -> BodyType:
    body_type = await _body_type(db, body_type_id)
    for field, value in body.model_dump().items():
        setattr(body_type, field, value)
    await db.commit()
    return body_type


async def create_position_type(
    db: AsyncSession, actor: Access, body: PositionTypeIn
) -> PositionType:
    await _body_type(db, body.body_type_id)
    sources = list(dict.fromkeys(body.derived_from))
    for source_id in sources:
        source = await _position_type(db, source_id)
        if source.is_derived:
            raise BadRequestError("Un cargo derivado no puede tomar a su titular de otro derivado.")
    values = body.model_dump(exclude={"derived_from", "default_role_id"})
    position = PositionType(
        **values,
        is_derived=bool(sources),
        # Derived positions are never appointed, so they grant no access of their own.
        default_role_id=None if sources else await _default_role(db, actor, body.default_role_id),
    )
    db.add(position)
    await _flush_unique(db, "un cargo")
    for source_id in sources:
        db.add(PositionDerivation(position_type_id=pk(position), source_position_type_id=source_id))
    await db.commit()
    return position


async def update_position_type(
    db: AsyncSession, actor: Access, position_type_id: uuid.UUID, body: PositionTypeUpdate
) -> PositionType:
    position = await _position_type(db, position_type_id)
    values = body.model_dump(exclude={"default_role_id"})
    for field, value in values.items():
        setattr(position, field, value)
    if body.default_role_id != position.default_role_id:
        if position.is_derived and body.default_role_id is not None:
            raise BadRequestError("Un cargo derivado no se nombra: no lleva rol por defecto.")
        position.default_role_id = await _default_role(db, actor, body.default_role_id)
    await db.commit()
    return position


async def derived_sources(db: AsyncSession, position_type_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.execute(
        select(col(PositionDerivation.source_position_type_id)).where(
            col(PositionDerivation.position_type_id) == position_type_id, _alive(PositionDerivation)
        )
    )
    return list(rows.scalars())


async def positions_by_id(
    db: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, PositionType]:
    if not ids:
        return {}
    rows = await db.execute(select(PositionType).where(col(PositionType.id).in_(ids)))
    return {pk(p): p for p in rows.scalars()}


async def incompatibilities(db: AsyncSession) -> list[PositionIncompatibility]:
    rows = await db.execute(
        select(PositionIncompatibility)
        .where(_alive(PositionIncompatibility))
        .order_by(col(PositionIncompatibility.created_at))
    )
    return list(rows.scalars())


async def add_incompatibility(db: AsyncSession, body: IncompatibilityIn) -> PositionIncompatibility:
    a, b = sorted([body.position_type_a_id, body.position_type_b_id])
    if a == b:
        raise BadRequestError("Un cargo no es incompatible consigo mismo.")
    for position_id in (a, b):
        if (await _position_type(db, position_id)).is_derived:
            raise BadRequestError(
                "Los cargos derivados no se nombran; no llevan incompatibilidades."
            )
    row = PositionIncompatibility(position_type_a_id=a, position_type_b_id=b, notes=body.notes)
    db.add(row)
    await _flush_unique(db, "una incompatibilidad")
    await db.commit()
    return row


async def remove_incompatibility(db: AsyncSession, incompatibility_id: uuid.UUID) -> None:
    row = await db.get(PositionIncompatibility, incompatibility_id)
    if row is None or row.deleted_at is not None:
        raise NotFoundError("Incompatibilidad no encontrada.")
    row.deleted_at = datetime.now(UTC)
    await db.commit()


async def coordination_position_types(db: AsyncSession) -> list[CoordinationPositionType]:
    rows = await db.execute(
        select(CoordinationPositionType)
        .where(_alive(CoordinationPositionType))
        .order_by(col(CoordinationPositionType.kind), col(CoordinationPositionType.sort_order))
    )
    return list(rows.scalars())


async def create_coordination_position_type(
    db: AsyncSession, actor: Access, body: CoordinationPositionTypeIn
) -> CoordinationPositionType:
    row = CoordinationPositionType(
        kind=CoordinationKind(body.kind),
        code=body.code,
        name=body.name,
        default_role_id=await _default_role(db, actor, body.default_role_id),
        sort_order=body.sort_order,
    )
    db.add(row)
    await _flush_unique(db, "un cargo de coordinación")
    await db.commit()
    return row


# --- bodies -----------------------------------------------------------------------------------

_NODE_LEVEL = {
    "municipality_id": (ScopeLevel.MUNICIPALITY, "municipalities", "municipality_id"),
    "federal_district_id": (
        ScopeLevel.FEDERAL_DISTRICT,
        "federal_districts",
        "federal_district_id",
    ),
    "local_district_id": (ScopeLevel.LOCAL_DISTRICT, "local_districts", "local_district_id"),
}


def visible_filter(geo: GeoScope) -> ColumnElement[bool] | None:
    """SQL filter over `party_structure.bodies`; None when the reader has no restriction."""
    if geo.unrestricted:
        return None
    node_clauses = " OR ".join(  # fixed columns; only scope SQL is interpolated
        f"(b.{column} IS NOT NULL AND EXISTS (SELECT 1 FROM geography.sections s "  # noqa: S608
        f"WHERE s.{link} = b.{column} AND s.is_active AND {geo.section_sql('s.id')}))"
        for column, (_, _, link) in _NODE_LEVEL.items()
    )
    return text(
        "EXISTS (SELECT 1 FROM party_structure.bodies b WHERE b.id = party_structure.bodies.id "  # noqa: S608
        "AND (b.framework_id IS NULL AND b.state_code IS NULL "
        "OR b.framework_id IS NULL AND EXISTS (SELECT 1 FROM geography.sections s "
        "JOIN geography.states st ON st.id = s.state_id JOIN geography.geographic_frameworks f "
        "ON f.id = st.framework_id AND f.is_active AND f.deleted_at IS NULL "
        f"WHERE st.state_code = b.state_code AND s.is_active AND {geo.section_sql('s.id')}) "
        f"OR {node_clauses}))"
    ).bindparams(**geo.sql_params)  # type: ignore[return-value]


async def list_bodies(
    db: AsyncSession,
    geo: GeoScope,
    params: PageParams,
    *,
    level: TerritorialLevel | None,
    body_type_id: uuid.UUID | None,
    state_code: int | None,
    include_dissolved: bool,
) -> CursorPage[Body]:
    statement = (
        select(Body).join(BodyType, col(BodyType.id) == col(Body.body_type_id)).where(_alive(Body))
    )
    visible = visible_filter(geo)
    if visible is not None:
        statement = statement.where(visible)
    if level is not None:
        statement = statement.where(col(BodyType.territorial_level) == level)
    if body_type_id is not None:
        statement = statement.where(col(Body.body_type_id) == body_type_id)
    if state_code is not None:
        statement = statement.where(col(Body.state_code) == state_code)
    if not include_dissolved:
        statement = statement.where(col(Body.dissolved_on).is_(None))
    sort = parse_sort(
        params.sort,
        allowed={"state_code": col(Body.state_code), "created_at": col(Body.created_at)},
        tiebreaker=col(Body.id),
        default="state_code",
    )
    page: CursorPage[Body] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def visible_body(db: AsyncSession, geo: GeoScope, body_id: uuid.UUID) -> Body:
    statement = select(Body).where(col(Body.id) == body_id, _alive(Body))
    visible = visible_filter(geo)
    if visible is not None:
        statement = statement.where(visible)
    found = (await db.execute(statement)).scalar_one_or_none()
    if found is None:
        raise NotFoundError("Órgano no encontrado.")
    return found


async def _node(db: AsyncSession, column: str, node_id: uuid.UUID, framework_id: uuid.UUID) -> int:
    """The node exists and is active in the active framework; returns its state code."""
    _, table, _ = _NODE_LEVEL[column]
    found = (
        await db.execute(
            text(
                f"SELECT st.state_code FROM geography.{table} n "  # noqa: S608 - fixed tables
                "JOIN geography.states st ON st.id = n.state_id "
                "WHERE n.id = :node AND n.framework_id = :fw AND n.is_active"
            ),
            {"node": node_id, "fw": framework_id},
        )
    ).scalar_one_or_none()
    if found is None:
        raise BadRequestError("El territorio no existe en el marco geográfico activo.")
    return int(found)


def _expected_columns(level: TerritorialLevel) -> tuple[str, ...]:
    if level == TerritorialLevel.MUNICIPAL:
        return ("municipality_id",)
    return ("federal_district_id", "local_district_id")


async def install_body(db: AsyncSession, geo: GeoScope, body: BodyInstallIn) -> Body:
    body_type = await _body_type(db, body.body_type_id)
    if not body_type.requires_installation:
        raise BadRequestError(
            "Los órganos nacionales y estatales ya están instalados; solo se instalan los "
            "comités distritales y municipales."
        )
    given = {
        column: getattr(body, column) for column in _NODE_LEVEL if getattr(body, column) is not None
    }
    expected = _expected_columns(TerritorialLevel(body_type.territorial_level))
    if len(given) != 1 or next(iter(given)) not in expected:
        raise BadRequestError(
            "Un comité municipal se instala en un municipio; uno distrital, en un distrito "
            "federal o local."
        )
    [(column, node_id)] = given.items()
    framework_id = await active_framework(db)
    state_code = await _node(db, column, node_id, framework_id)
    await ensure_node_within(db, geo, _NODE_LEVEL[column][0], node_id)
    installed = Body(
        body_type_id=pk(body_type),
        state_code=state_code,
        framework_id=framework_id,
        installed_on=body.installed_on,
        installation_agreement=body.installation_agreement,
        district_kind=(
            None
            if column == "municipality_id"
            else DistrictKind.FEDERAL
            if column == "federal_district_id"
            else DistrictKind.LOCAL
        ),
        **{column: node_id},
    )
    db.add(installed)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise ConflictError("Ese órgano ya está instalado en ese territorio.") from error
    await db.commit()
    return installed


async def dissolve_body(
    db: AsyncSession, geo: GeoScope, body_id: uuid.UUID, body: BodyDissolveIn
) -> Body:
    found = await visible_body(db, geo, body_id)
    body_type = await _body_type(db, found.body_type_id)
    if not body_type.requires_installation:
        raise ConflictError("Los órganos nacionales y estatales no se disuelven.")
    if found.dissolved_on is not None:
        raise ConflictError("El órgano ya está disuelto.")
    if found.installed_on is not None and body.dissolved_on < found.installed_on:
        raise BadRequestError("La disolución no puede ser anterior a la instalación.")
    column = next(c for c in _NODE_LEVEL if getattr(found, c) is not None)
    await ensure_node_within(db, geo, _NODE_LEVEL[column][0], getattr(found, column))
    found.dissolved_on = body.dissolved_on
    found.dissolution_agreement = body.dissolution_agreement
    await db.commit()
    return found


async def territory_names(db: AsyncSession, bodies: Sequence[Body]) -> dict[uuid.UUID, str]:
    """Readable territory of each body in the active framework."""
    names: dict[uuid.UUID, str] = {}
    states = {
        int(code): name
        for code, name in (
            await db.execute(
                text(
                    "SELECT st.state_code, st.name FROM geography.states st "
                    "JOIN geography.geographic_frameworks f ON f.id = st.framework_id "
                    "WHERE f.is_active AND f.deleted_at IS NULL"
                )
            )
        ).all()
    }
    queries = {
        "municipality_id": "SELECT id, name FROM geography.municipalities WHERE id = ANY(:ids)",
        "federal_district_id": (
            "SELECT id, 'Distrito federal ' || district_number FROM geography.federal_districts "
            "WHERE id = ANY(:ids)"
        ),
        "local_district_id": (
            "SELECT id, 'Distrito local ' || district_number FROM geography.local_districts "
            "WHERE id = ANY(:ids)"
        ),
    }
    nodes: dict[uuid.UUID, str] = {}
    for column, sql in queries.items():
        ids = [getattr(b, column) for b in bodies if getattr(b, column) is not None]
        if ids:
            nodes.update(dict((await db.execute(text(sql), {"ids": ids})).all()))
    for b in bodies:
        node = b.municipality_id or b.federal_district_id or b.local_district_id
        state = states.get(b.state_code or 0, f"Estado {b.state_code}") if b.state_code else None
        if node is not None:
            names[pk(b)] = (
                f"{nodes.get(node, 'Territorio')}, {state}" if state else nodes.get(node, "")
            )
        else:
            names[pk(b)] = state or "Nacional"
    return names
