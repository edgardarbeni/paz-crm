"""/party-structure — statutory catalog and installed bodies (phase 1, D-105 and D-107)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.core.db.base import pk
from app.core.db.session import SessionDep
from app.core.pagination import CursorPage, PageParams, page_params
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.schemas import RoleSummary
from app.modules.party_structure import service
from app.modules.party_structure.models import (
    Body,
    BodyType,
    CoordinationPositionType,
    PositionType,
    TerritorialLevel,
)
from app.modules.party_structure.permissions import StructurePerm
from app.modules.party_structure.schemas import (
    BodyDissolveIn,
    BodyInstallIn,
    BodyOut,
    BodyTypeIn,
    BodyTypeOut,
    BodyTypeRef,
    BodyTypeUpdate,
    CoordinationPositionTypeIn,
    CoordinationPositionTypeOut,
    IncompatibilityIn,
    IncompatibilityOut,
    PositionTypeIn,
    PositionTypeOut,
    PositionTypeRef,
    PositionTypeUpdate,
)

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
