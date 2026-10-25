"""Geography queries (D-19, D-34). Every query is limited to the active framework and to the
caller's geographic scope at the SQL level."""

import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, exists, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from sqlmodel import col

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.geography.models import (
    Block,
    ElectoralRegion,
    FederalDistrict,
    GeographicFramework,
    LocalDistrict,
    Locality,
    LocalitySection,
    Municipality,
    Neighborhood,
    NeighborhoodSection,
    Section,
    State,
)
from app.modules.identity.services.scopes import GeoScope


class NoActiveFrameworkError(NotFoundError):
    code = "no-active-framework"
    title = "No hay geografía cargada"


async def active_framework(db: AsyncSession) -> GeographicFramework:
    framework = (
        await db.execute(
            select(GeographicFramework).where(
                col(GeographicFramework.is_active).is_(True),
                col(GeographicFramework.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    if framework is None:
        raise NoActiveFrameworkError("No hay un marco geográfico activo. Importa la geografía.")
    return framework


# --- levels ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LevelDef:
    name: str
    model: type[Any]
    code: Mapped[Any]
    label: Mapped[Any] | None
    parents: dict[str, Mapped[Any]]
    tile_min_zoom: int

    def visible(self, geo: GeoScope) -> ColumnElement[bool] | None:  # noqa: PLR0911
        """EXISTS predicate: the node touches at least one section of the user's scope."""
        if geo.unrestricted:
            return None
        model = self.model

        def through_sections(link: Mapped[Any]) -> ColumnElement[bool]:
            return exists(
                select(literal(1))
                .select_from(Section)
                .where(link == model.id, geo.sections_filter(col(Section.id)))  # type: ignore[arg-type]
            )

        match self.name:
            case "section":
                return geo.sections_filter(col(Section.id))
            case "state":
                return through_sections(col(Section.state_id))
            case "municipality":
                return through_sections(col(Section.municipality_id))
            case "federal_district":
                return through_sections(col(Section.federal_district_id))
            case "local_district":
                return through_sections(col(Section.local_district_id))
            case "electoral_region":
                return exists(
                    select(literal(1))
                    .select_from(Section)
                    .join(State, col(State.id) == col(Section.state_id))
                    .where(
                        col(State.electoral_region_id) == model.id,
                        geo.sections_filter(col(Section.id)),  # type: ignore[arg-type]
                    )
                )
            case "locality":
                return or_(
                    exists(
                        select(literal(1))
                        .select_from(LocalitySection)
                        .where(
                            col(LocalitySection.locality_id) == model.id,
                            geo.sections_filter(col(LocalitySection.section_id)),  # type: ignore[arg-type]
                        )
                    ),
                    exists(
                        select(literal(1))
                        .select_from(Block)
                        .where(
                            col(Block.locality_id) == model.id,
                            geo.sections_filter(col(Block.section_id)),  # type: ignore[arg-type]
                        )
                    ),
                )
            case "neighborhood":
                return exists(
                    select(literal(1))
                    .select_from(NeighborhoodSection)
                    .where(
                        col(NeighborhoodSection.neighborhood_id) == model.id,
                        geo.sections_filter(col(NeighborhoodSection.section_id)),  # type: ignore[arg-type]
                    )
                )
        raise AssertionError(self.name)  # pragma: no cover


LEVELS: dict[str, LevelDef] = {
    level.name: level
    for level in (
        LevelDef(
            "electoral_region", ElectoralRegion, col(ElectoralRegion.region_number), None, {}, 0
        ),
        LevelDef(
            "state",
            State,
            col(State.state_code),
            col(State.name),
            {"electoral_region_id": col(State.electoral_region_id)},
            0,
        ),
        LevelDef(
            "federal_district",
            FederalDistrict,
            col(FederalDistrict.district_number),
            None,
            {"state_id": col(FederalDistrict.state_id)},
            5,
        ),
        LevelDef(
            "local_district",
            LocalDistrict,
            col(LocalDistrict.district_number),
            None,
            {"state_id": col(LocalDistrict.state_id)},
            5,
        ),
        LevelDef(
            "municipality",
            Municipality,
            col(Municipality.municipality_code),
            col(Municipality.name),
            {"state_id": col(Municipality.state_id)},
            6,
        ),
        LevelDef(
            "section",
            Section,
            col(Section.section_number),
            None,
            {
                "state_id": col(Section.state_id),
                "municipality_id": col(Section.municipality_id),
                "federal_district_id": col(Section.federal_district_id),
                "local_district_id": col(Section.local_district_id),
            },
            9,
        ),
        LevelDef(
            "locality",
            Locality,
            col(Locality.locality_code),
            col(Locality.name),
            {"state_id": col(Locality.state_id), "municipality_id": col(Locality.municipality_id)},
            10,
        ),
        LevelDef(
            "neighborhood",
            Neighborhood,
            col(Neighborhood.source_key),
            col(Neighborhood.name),
            {
                "state_id": col(Neighborhood.state_id),
                "municipality_id": col(Neighborhood.municipality_id),
            },
            12,
        ),
    )
}


def level_def(name: str) -> LevelDef:
    try:
        return LEVELS[name]
    except KeyError:
        raise NotFoundError(f"Nivel geográfico desconocido: {name}.") from None


def format_key(level: str, state_code: int | None, row: dict[str, Any]) -> str:  # noqa: PLR0911
    """Human INE key (D-19): 01 · 01-005 (municipio) · 01-03 (distrito) · 01-0338 (sección)."""
    code = row["code"]
    state = f"{state_code:02d}" if state_code is not None else "--"
    match level:
        case "electoral_region":
            return f"C{code}"
        case "state":
            return f"{code:02d}"
        case "municipality":
            return f"{state}-{code:03d}"
        case "federal_district" | "local_district":
            return f"{state}-{code:02d}"
        case "section":
            return f"{state}-{code:04d}"
        case "locality":
            return f"{state}-{row.get('municipality_code', 0):03d}-{code:04d}"
        case _:
            return f"{state}-COL-{code}"


def _node_select(level: LevelDef) -> Select[Any]:
    model = level.model
    columns: list[Any] = [
        col(model.id).label("id"),
        level.code.label("code"),
        (level.label if level.label is not None else literal(None)).label("name"),
        *(column.label(name) for name, column in level.parents.items()),
    ]
    statement = select(*columns)
    if level.name == "state":
        statement = statement.add_columns(col(State.state_code).label("state_code"))
    elif "state_id" in level.parents:
        statement = statement.add_columns(col(State.state_code).label("state_code")).join(
            State, col(State.id) == level.parents["state_id"]
        )
    else:
        statement = statement.add_columns(literal(None).label("state_code"))
    if level.name == "locality":
        statement = statement.add_columns(
            col(Municipality.municipality_code).label("municipality_code")
        ).join(Municipality, col(Municipality.id) == col(Locality.municipality_id))
    return statement


def node_payload(level: str, row: dict[str, Any]) -> dict[str, Any]:
    parents = {name: row.get(name) for name in LEVELS[level].parents}
    return {
        "id": row["id"],
        "level": level,
        "code": str(row["code"]),
        "key": format_key(level, row.get("state_code"), row),
        "name": row.get("name"),
        "state_code": row.get("state_code"),
        **parents,
    }


async def list_nodes(
    db: AsyncSession,
    geo: GeoScope,
    level_name: str,
    params: PageParams,
    *,
    parents: dict[str, uuid.UUID],
    search: str | None,
) -> CursorPage[dict[str, Any]]:
    level = level_def(level_name)
    framework = await active_framework(db)
    model = level.model
    statement = _node_select(level).where(
        col(model.framework_id) == framework.id, col(model.is_active).is_(True)
    )
    for name, value in parents.items():
        if name not in level.parents:
            raise BadRequestError(f"El nivel {level.name} no se filtra por {name}.")
        statement = statement.where(level.parents[name] == value)
    if search:
        if level.label is None:
            raise BadRequestError(f"El nivel {level.name} no tiene nombre para buscar.")
        statement = statement.where(
            func.f_unaccent(func.lower(level.label)).ilike(f"%{_normalize(search)}%")
        )
    visible = level.visible(geo)
    if visible is not None:
        statement = statement.where(visible)
    allowed: dict[str, Any] = {"code": level.code}
    if level.label is not None:
        allowed["name"] = level.label
    if "state_id" in level.parents or level.name == "state":
        allowed["state_code"] = col(State.state_code)
    sort = parse_sort(params.sort, allowed=allowed, tiebreaker=col(model.id), default="code")
    page = await paginate(db, statement, sort=sort, limit=params.limit, cursor=params.cursor)
    return CursorPage[dict[str, Any]](
        items=[node_payload(level.name, row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


def _normalize(value: str) -> str:
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(ch) != "Mn"
    )
    return stripped.replace("%", r"\%").replace("_", r"\_").strip()


async def get_node(
    db: AsyncSession, geo: GeoScope, level_name: str, node_id: uuid.UUID, *, geometry: bool
) -> dict[str, Any]:
    level = level_def(level_name)
    framework = await active_framework(db)
    model = level.model
    statement = _node_select(level).where(
        col(model.id) == node_id, col(model.framework_id) == framework.id
    )
    if geometry:
        statement = statement.add_columns(
            func.ST_AsGeoJSON(func.ST_SimplifyPreserveTopology(col(model.geom), 0.0001), 6).label(
                "geojson"
            ),
            func.ST_XMin(col(model.geom)).label("xmin"),
            func.ST_YMin(col(model.geom)).label("ymin"),
            func.ST_XMax(col(model.geom)).label("xmax"),
            func.ST_YMax(col(model.geom)).label("ymax"),
        )
    row = (await db.execute(statement)).mappings().one_or_none()
    if row is None:
        raise NotFoundError("Nodo geográfico no encontrado.")
    visible = level.visible(geo)
    if visible is not None:
        allowed = (
            await db.execute(
                select(literal(1)).select_from(model).where(col(model.id) == node_id, visible)
            )
        ).first()
        if allowed is None:
            raise ForbiddenError("El nodo está fuera de tu alcance geográfico.")
    payload = node_payload(level.name, dict(row))
    if geometry:
        payload["geometry"] = json.loads(row["geojson"]) if row["geojson"] else None
        payload["bbox"] = (
            [row["xmin"], row["ymin"], row["xmax"], row["ymax"]]
            if row["xmin"] is not None
            else None
        )
    if level.name == "section":
        payload["ancestors"] = await _section_ancestors(db, node_id)
        payload["block_count"] = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Block)
                    .where(col(Block.section_id) == node_id, col(Block.is_active).is_(True))
                )
            ).scalar_one()
        )
    return payload


_ANCESTORS_SQL = """
    SELECT s.id AS section_id, s.section_number, st.id AS state_id, st.state_code, st.name AS state_name,
           r.id AS electoral_region_id, r.region_number,
           mu.id AS municipality_id, mu.municipality_code, mu.name AS municipality_name,
           fd.id AS federal_district_id, fd.district_number AS federal_district_number,
           ld.id AS local_district_id, ld.district_number AS local_district_number
    FROM geography.sections s
    JOIN geography.states st ON st.id = s.state_id
    LEFT JOIN geography.electoral_regions r ON r.id = st.electoral_region_id
    JOIN geography.municipalities mu ON mu.id = s.municipality_id
    JOIN geography.federal_districts fd ON fd.id = s.federal_district_id
    JOIN geography.local_districts ld ON ld.id = s.local_district_id
"""


def _ancestors_payload(row: dict[str, Any]) -> dict[str, Any]:
    state = row["state_code"]
    return {
        "section": {"id": row["section_id"], "key": f"{state:02d}-{row['section_number']:04d}"},
        "municipality": {
            "id": row["municipality_id"],
            "key": f"{state:02d}-{row['municipality_code']:03d}",
            "name": row["municipality_name"],
        },
        "federal_district": {
            "id": row["federal_district_id"],
            "key": f"{state:02d}-{row['federal_district_number']:02d}",
        },
        "local_district": {
            "id": row["local_district_id"],
            "key": f"{state:02d}-{row['local_district_number']:02d}",
        },
        "state": {"id": row["state_id"], "key": f"{state:02d}", "name": row["state_name"]},
        "electoral_region": (
            {"id": row["electoral_region_id"], "key": f"C{row['region_number']}"}
            if row["electoral_region_id"]
            else None
        ),
    }


async def _section_ancestors(db: AsyncSession, section_id: uuid.UUID) -> dict[str, Any]:
    row = (
        (await db.execute(text(_ANCESTORS_SQL + " WHERE s.id = :id"), {"id": section_id}))
        .mappings()
        .one()
    )
    return _ancestors_payload(dict(row))


async def locate(
    db: AsyncSession, geo: GeoScope, *, longitude: float, latitude: float
) -> dict[str, Any]:
    """Point-in-polygon on subdivided sections, then ancestors by FK (D-19, < 50 ms p95)."""
    framework = await active_framework(db)
    row = (
        (
            await db.execute(
                text(
                    "WITH hit AS (SELECT sp.section_id FROM geography.section_parts sp "
                    "JOIN geography.sections s0 ON s0.id = sp.section_id "
                    "WHERE s0.framework_id = :fw AND s0.is_active "
                    "AND ST_Intersects(sp.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) LIMIT 1) "
                    + _ANCESTORS_SQL
                    + " JOIN hit ON hit.section_id = s.id"
                ),
                {"fw": framework.id, "lon": longitude, "lat": latitude},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise NotFoundError("La coordenada no cae en ninguna sección del marco activo.")
    visible = geo.sections_filter(col(Section.id))
    if visible is not None:
        allowed = (
            await db.execute(
                select(literal(1))
                .select_from(Section)
                .where(col(Section.id) == row["section_id"], visible)
            )
        ).first()
        if allowed is None:
            raise ForbiddenError("La coordenada está fuera de tu alcance geográfico.")
    return _ancestors_payload(dict(row))


# --- search ----------------------------------------------------------------------------------

_KEY = re.compile(r"^\s*(\d{1,2})\s*[-/ .]\s*(\d{1,4})\s*$")
_COMPACT = re.compile(r"^\s*(\d{2})(\d{3,4})\s*$")
_NUMBER = re.compile(r"^\s*(\d{1,4})\s*$")
_KEY_LEVELS = ("section", "municipality", "federal_district", "local_district")


async def search(  # noqa: PLR0912
    db: AsyncSession, geo: GeoScope, query: str, *, levels: list[str] | None, limit: int
) -> list[dict[str, Any]]:
    """Flexible INE key search ('09-0123', '9 123', '090123', '338') or accent-insensitive
    name search (municipalities, localities, colonias, states)."""
    framework = await active_framework(db)
    wanted = levels or []
    state_code: int | None = None
    number: int | None = None
    if match := _KEY.match(query):
        state_code, number = int(match.group(1)), int(match.group(2))
    elif match := _COMPACT.match(query):
        state_code, number = int(match.group(1)), int(match.group(2))
        if not wanted:
            wanted = ["section"] if len(match.group(2)) == 4 else ["municipality"]
    elif match := _NUMBER.match(query):
        number = int(match.group(1))

    results: list[dict[str, Any]] = []
    if number is not None:
        for name in wanted or list(_KEY_LEVELS):
            if name not in _KEY_LEVELS:
                continue
            level = LEVELS[name]
            statement = _node_select(level).where(
                col(level.model.framework_id) == framework.id,
                col(level.model.is_active).is_(True),
                level.code == number,
            )
            if state_code is not None:
                statement = statement.where(col(State.state_code) == state_code)
            visible = level.visible(geo)
            if visible is not None:
                statement = statement.where(visible)
            rows = (
                await db.execute(statement.order_by(col(State.state_code)).limit(limit))
            ).mappings()
            results.extend(node_payload(name, dict(row)) for row in rows)
        return results[:limit]

    term = _normalize(query)
    if len(term) < 3:
        raise BadRequestError("Escribe al menos 3 caracteres o una clave (p. ej. 09-0123).")
    for name in wanted or ["state", "municipality", "locality", "neighborhood"]:
        level = level_def(name)
        if level.label is None:
            continue
        normalized = func.f_unaccent(func.lower(level.label))
        statement = _node_select(level).where(
            col(level.model.framework_id) == framework.id,
            col(level.model.is_active).is_(True),
            normalized.ilike(f"%{term}%"),
        )
        visible = level.visible(geo)
        if visible is not None:
            statement = statement.where(visible)
        statement = statement.order_by(
            func.similarity(normalized, term).desc(), col(level.model.id)
        ).limit(limit)
        results.extend(
            node_payload(name, dict(row)) for row in (await db.execute(statement)).mappings()
        )
    return results[:limit]


# --- vector tiles ----------------------------------------------------------------------------

TILE_LAYERS = {
    "states": ("states", "s.state_code::text", "s.name", "s.id", 0),
    "federal_districts": ("federal_districts", "s.district_number::text", "NULL", "s.id", 5),
    "local_districts": ("local_districts", "s.district_number::text", "NULL", "s.id", 5),
    "municipalities": ("municipalities", "s.municipality_code::text", "s.name", "s.id", 6),
    "sections": ("sections", "s.section_number::text", "NULL", "s.id", 9),
    "neighborhoods": ("neighborhoods", "s.source_key", "s.name", "s.id", 12),
    "blocks": ("blocks", "s.block_number::text", "NULL", "s.section_id", 14),
}
_TILE_SCOPE = {
    "states": "EXISTS (SELECT 1 FROM geography.sections x JOIN identity.user_scope_sections u ON u.section_id = x.id WHERE x.state_id = s.id AND u.user_id = :user)",
    "federal_districts": "EXISTS (SELECT 1 FROM geography.sections x JOIN identity.user_scope_sections u ON u.section_id = x.id WHERE x.federal_district_id = s.id AND u.user_id = :user)",
    "local_districts": "EXISTS (SELECT 1 FROM geography.sections x JOIN identity.user_scope_sections u ON u.section_id = x.id WHERE x.local_district_id = s.id AND u.user_id = :user)",
    "municipalities": "EXISTS (SELECT 1 FROM geography.sections x JOIN identity.user_scope_sections u ON u.section_id = x.id WHERE x.municipality_id = s.id AND u.user_id = :user)",
    "sections": "EXISTS (SELECT 1 FROM identity.user_scope_sections u WHERE u.section_id = s.id AND u.user_id = :user)",
    "neighborhoods": "EXISTS (SELECT 1 FROM geography.neighborhood_sections x JOIN identity.user_scope_sections u ON u.section_id = x.section_id WHERE x.neighborhood_id = s.id AND u.user_id = :user)",
    "blocks": "EXISTS (SELECT 1 FROM identity.user_scope_sections u WHERE u.section_id = s.section_id AND u.user_id = :user)",
}


def tile_bounds_ok(z: int, x: int, y: int) -> bool:
    return 0 <= z <= 22 and 0 <= x < 2**z and 0 <= y < 2**z


async def tile(db: AsyncSession, geo: GeoScope, layer: str, z: int, x: int, y: int) -> bytes:  # noqa: PLR0917
    if layer not in TILE_LAYERS:
        raise NotFoundError(f"Capa de teselas desconocida: {layer}.")
    if not tile_bounds_ok(z, x, y):
        raise BadRequestError("Coordenadas de tesela fuera de rango.")
    table, code, name, node, min_zoom = TILE_LAYERS[layer]
    framework = await active_framework(db)
    if z < min_zoom:
        return b""
    scope = "" if geo.unrestricted else f"AND {_TILE_SCOPE[layer]}"
    sql = f"""
        WITH bounds AS (
          SELECT ST_TileEnvelope(:z, :x, :y) AS env,
                 ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => 0.015625), 4326) AS env4326
        ), features AS (
          SELECT {node} AS id, {code} AS code, {name} AS name,
                 ST_AsMVTGeom(ST_Transform(s.geom, 3857), bounds.env, 4096, 64, true) AS geom
          FROM geography.{table} s, bounds
          WHERE s.framework_id = :fw AND s.is_active AND s.geom && bounds.env4326 {scope}
        )
        SELECT ST_AsMVT(features, :layer, 4096, 'geom') FROM features WHERE geom IS NOT NULL
    """
    params: dict[str, Any] = {"z": z, "x": x, "y": y, "fw": framework.id, "layer": layer}
    if not geo.unrestricted:
        params["user"] = geo.user_id
    data = (await db.execute(text(sql), params)).scalar_one()
    return bytes(data or b"")
