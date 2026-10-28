"""/geography — read-only electoral geography (D-19) limited by the caller's scope (D-34)."""

import base64
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy import select
from sqlmodel import col

from app.core.db.session import SessionDep
from app.core.errors import NotFoundError
from app.core.pagination import CursorPage, PageParams, SortField, page_params, paginate
from app.core.redis import RedisDep
from app.modules.geography import service
from app.modules.geography.models import GeographicFramework, ImportIssue, ImportRun
from app.modules.geography.schemas import (
    Ancestors,
    FrameworkOut,
    GeoNodeDetail,
    GeoNodeOut,
    ImportIssueOut,
    ImportRunOut,
    Level,
)
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm

router = APIRouter(prefix="/geography", tags=["geography"])

GeoReader = Annotated[CurrentUser, permission(Perm.GEOGRAPHY_READ)]
ImportReader = Annotated[CurrentUser, permission(Perm.GEOGRAPHY_IMPORT_READ)]
MVT = "application/vnd.mapbox-vector-tile"


@router.get("/frameworks", operation_id="listFrameworks", summary="Marcos geográficos")
async def list_frameworks(db: SessionDep, _: GeoReader) -> list[FrameworkOut]:
    rows = await db.execute(
        select(GeographicFramework)
        .where(col(GeographicFramework.deleted_at).is_(None))
        .order_by(col(GeographicFramework.created_at).desc())
    )
    return [FrameworkOut.model_validate(row) for row in rows.scalars()]


@router.get(
    "/search",
    operation_id="searchGeography",
    summary="Buscar por clave INE, número o nombre, con el estado",
)
async def search(
    db: SessionDep,
    user: GeoReader,
    q: Annotated[
        str,
        Query(min_length=1, max_length=100, examples=["01-0338", "338 Aguascalientes", "Calvillo"]),
    ],
    level: Annotated[list[Level] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    state_id: Annotated[
        uuid.UUID | None, Query(description="Limita los resultados a un estado.")
    ] = None,
) -> list[GeoNodeOut]:
    rows = await service.search(
        db,
        user.geo,
        q,
        levels=list(level) if level else None,
        limit=limit,
        state_id=state_id,
    )
    return [GeoNodeOut.model_validate(row) for row in rows]


@router.get(
    "/locate",
    operation_id="locatePoint",
    summary="¿A qué sección pertenece una coordenada? (y sus ancestros)",
)
async def locate(
    db: SessionDep,
    user: GeoReader,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> Ancestors:
    return Ancestors.model_validate(await service.locate(db, user.geo, longitude=lon, latitude=lat))


@router.get(
    "/tiles/{layer}/{z}/{x}/{y}.mvt",
    operation_id="getVectorTile",
    summary="Tesela vectorial (MVT) por capa",
    response_class=Response,
    responses={200: {"content": {MVT: {}}}},
)
async def get_tile(
    request: Request,
    db: SessionDep,
    redis: RedisDep,
    user: GeoReader,
    layer: Annotated[str, Path(pattern=r"^[a-z_]+$")],
    z: int,
    x: int,
    y: int,
) -> Response:
    framework = await service.active_framework(db)
    # v2: tiles built from generalized geometries (D-80); older keys expire on their own.
    cache_key = f"tile:v2:{framework.id}:{layer}:{z}/{x}/{y}" if user.geo.unrestricted else None
    data: bytes | None = None
    if cache_key:
        cached = await redis.get(cache_key)
        if cached is not None:
            data = base64.b64decode(cached)
    if data is None:
        data = await service.tile(db, user.geo, layer, z, x, y)
        if cache_key:
            ttl = request.app.state.settings.geo_tile_cache_seconds
            await redis.set(cache_key, base64.b64encode(data).decode(), ex=ttl)
    return Response(
        content=data,
        media_type=MVT,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/import-runs", operation_id="listImportRuns", summary="Corridas de importación")
async def list_import_runs(
    db: SessionDep,
    _: ImportReader,
    params: Annotated[PageParams, Depends(page_params)],
    state_code: Annotated[int | None, Query(ge=1, le=32)] = None,
) -> CursorPage[ImportRunOut]:
    statement = select(ImportRun)
    if state_code is not None:
        statement = statement.where(col(ImportRun.state_code) == state_code)
    page = await paginate(
        db,
        statement,
        sort=[
            SortField("started_at", col(ImportRun.started_at), True),
            SortField("id", col(ImportRun.id), True),
        ],
        limit=params.limit,
        cursor=params.cursor,
    )
    return CursorPage[ImportRunOut](
        items=[ImportRunOut.model_validate(run) for run in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/import-runs/{run_id}", operation_id="getImportRun", summary="Detalle de una corrida")
async def get_import_run(run_id: uuid.UUID, db: SessionDep, _: ImportReader) -> ImportRunOut:
    run = await db.get(ImportRun, run_id)
    if run is None:
        raise NotFoundError("Corrida de importación no encontrada.")
    return ImportRunOut.model_validate(run)


@router.get(
    "/import-runs/{run_id}/issues",
    operation_id="listImportIssues",
    summary="Errores y advertencias",
)
async def list_import_issues(
    run_id: uuid.UUID,
    db: SessionDep,
    _: ImportReader,
    params: Annotated[PageParams, Depends(page_params)],
    severity: Annotated[str | None, Query(pattern="^(error|warning)$")] = None,
    code: Annotated[str | None, Query(max_length=50)] = None,
) -> CursorPage[ImportIssueOut]:
    statement = select(ImportIssue).where(col(ImportIssue.import_run_id) == run_id)
    if severity:
        statement = statement.where(col(ImportIssue.severity) == severity)
    if code:
        statement = statement.where(col(ImportIssue.code) == code)
    page = await paginate(
        db,
        statement,
        sort=[SortField("id", col(ImportIssue.id))],
        limit=params.limit,
        cursor=params.cursor,
    )
    return CursorPage[ImportIssueOut](
        items=[ImportIssueOut.model_validate(issue) for issue in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{level}", operation_id="listGeoNodes", summary="Listar nodos de un nivel")
async def list_nodes(
    level: Level,
    db: SessionDep,
    user: GeoReader,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Número (clave del nivel) o nombre; en distritos y secciones, el estado.",
        ),
    ] = None,
    electoral_region_id: uuid.UUID | None = None,
    state_id: uuid.UUID | None = None,
    municipality_id: uuid.UUID | None = None,
    federal_district_id: uuid.UUID | None = None,
    local_district_id: uuid.UUID | None = None,
) -> CursorPage[GeoNodeOut]:
    parents = {
        name: value
        for name, value in {
            "electoral_region_id": electoral_region_id,
            "state_id": state_id,
            "municipality_id": municipality_id,
            "federal_district_id": federal_district_id,
            "local_district_id": local_district_id,
        }.items()
        if value is not None
    }
    page = await service.list_nodes(db, user.geo, level, params, parents=parents, search=q)
    return CursorPage[GeoNodeOut](
        items=[GeoNodeOut.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{level}/{node_id}", operation_id="getGeoNode", summary="Detalle de un nodo")
async def get_node(
    level: Level,
    node_id: uuid.UUID,
    db: SessionDep,
    user: GeoReader,
    geometry: Annotated[bool, Query(description="Incluir GeoJSON simplificado.")] = False,
) -> GeoNodeDetail:
    return GeoNodeDetail.model_validate(
        await service.get_node(db, user.geo, level, node_id, geometry=geometry)
    )
