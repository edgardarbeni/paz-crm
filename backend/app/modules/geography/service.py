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
from app.modules.geography.generalize import tile_geometry
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
    state_columns: tuple[Any, ...] = (
        col(State.state_code).label("state_code"),
        col(State.name).label("state_name"),
    )
    if level.name == "state":
        statement = statement.add_columns(*state_columns)
    elif "state_id" in level.parents:
        statement = statement.add_columns(*state_columns).join(
            State, col(State.id) == level.parents["state_id"]
        )
    else:
        statement = statement.add_columns(
            literal(None).label("state_code"), literal(None).label("state_name")
        )
    if "municipality_id" in level.parents:
        # Context for pickers: sections, localities and colonias repeat names across municipalities.
        statement = statement.add_columns(
            col(Municipality.municipality_code).label("municipality_code"),
            col(Municipality.name).label("municipality_name"),
        ).join(Municipality, col(Municipality.id) == level.parents["municipality_id"])
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
        "state_name": row.get("state_name"),
        "municipality_name": row.get("municipality_name"),
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
        statement = statement.where(_list_search(level, search))
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


def _list_search(level: LevelDef, search: str) -> ColumnElement[bool]:
    """Explorer filter (D-79): a number matches the INE code; text matches the name, or the
    state's name for levels without one (districts, sections)."""
    if match := _NUMBER.match(search):
        return level.code == int(match.group(1))
    if len(search.strip()) < 2:
        raise BadRequestError("Escribe al menos 2 caracteres o un número.")
    label = level.label
    if label is None:
        if level.name == "electoral_region":
            raise BadRequestError("Las circunscripciones se buscan por número.")
        label = col(State.name)
    return func.f_unaccent(func.lower(label)).ilike(f"%{_normalize(search)}%")


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


# What each level contains: (child level, filter of the child that points to the parent).
CHILDREN: dict[str, tuple[tuple[str, str], ...]] = {
    "electoral_region": (("state", "electoral_region_id"),),
    "state": (
        ("municipality", "state_id"),
        ("federal_district", "state_id"),
        ("local_district", "state_id"),
        ("section", "state_id"),
    ),
    "municipality": (
        ("section", "municipality_id"),
        ("locality", "municipality_id"),
        ("neighborhood", "municipality_id"),
    ),
    "federal_district": (("section", "federal_district_id"),),
    "local_district": (("section", "local_district_id"),),
}


async def node_children(
    db: AsyncSession, geo: GeoScope, level_name: str, node_id: uuid.UUID
) -> list[dict[str, Any]]:
    """How many nodes of each child level the node contains, within the caller's scope."""
    level = level_def(level_name)
    framework = await active_framework(db)
    model = level.model
    exists_row = (
        await db.execute(
            select(literal(1))
            .select_from(model)
            .where(col(model.id) == node_id, col(model.framework_id) == framework.id)
        )
    ).first()
    if exists_row is None:
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
    groups: list[dict[str, Any]] = []
    for child_name, parent_filter in CHILDREN.get(level.name, ()):
        child = LEVELS[child_name]
        statement = (
            select(func.count())
            .select_from(child.model)
            .where(
                col(child.model.framework_id) == framework.id,
                col(child.model.is_active).is_(True),
                child.parents[parent_filter] == node_id,
            )
        )
        child_visible = child.visible(geo)
        if child_visible is not None:
            statement = statement.where(child_visible)
        count = int((await db.execute(statement)).scalar_one())
        groups.append({"level": child_name, "parent_filter": parent_filter, "count": count})
    return groups


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
_NAMED_LEVELS = ("state", "municipality", "locality", "neighborhood")
# Words that only say which level is meant ("sección 338", "df 3 jalisco"); they are dropped
# when the query carries a number, and they narrow the levels when the caller sent none.
_LEVEL_WORDS: dict[str, tuple[str, ...]] = {
    "seccion": ("section",),
    "secc": ("section",),
    "sec": ("section",),
    "distrito": ("federal_district", "local_district"),
    "dto": ("federal_district", "local_district"),
    "df": ("federal_district",),
    "federal": ("federal_district",),
    "dl": ("local_district",),
    "local": ("local_district",),
    "municipio": ("municipality",),
    "mpio": ("municipality",),
}
_FILLER = {"de", "del", "en", "la", "el", "no", "num", "numero"}


def _fold(value: str) -> str:
    """Lowercase without accents or punctuation, for comparisons done in Python."""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(ch) != "Mn"
    )
    return " ".join(re.sub(r"[^\w#]+", " ", stripped).split())


@dataclass(frozen=True)
class _StateRef:
    id: uuid.UUID
    name: str  # folded


async def _states(db: AsyncSession, framework: GeographicFramework) -> list[_StateRef]:
    rows = await db.execute(
        select(col(State.id), col(State.name)).where(
            col(State.framework_id) == framework.id, col(State.is_active).is_(True)
        )
    )
    return [_StateRef(row.id, _fold(row.name)) for row in rows]


def _match_states(states: list[_StateRef], text: str) -> list[uuid.UUID]:
    """States named by `text`: exact name, else every state with a word starting with it
    ("prueba", "agua", "mexico" → México; "ciudad de mexico" → only CDMX)."""
    if len(text) < 3 or set(text.split()) <= _FILLER:
        return []
    exact = [state.id for state in states if state.name == text]
    if exact:
        return exact
    return [
        state.id
        for state in states
        if state.name.startswith(text) or f" {text}" in f" {state.name}"
    ]


def _strip_filler(words: list[str]) -> list[str]:
    while words and words[0] in _FILLER:
        words = words[1:]
    while words and words[-1] in _FILLER:
        words = words[:-1]
    return words


def _split_state(
    states: list[_StateRef], words: list[str]
) -> tuple[list[uuid.UUID], list[str]] | None:
    """The longest leading or trailing run of words that names a state, and the rest:
    "centro aguascalientes" → (Aguascalientes, ["centro"])."""
    for size in range(len(words), 0, -1):
        for candidate, rest in (
            (words[-size:], words[:-size]),
            (words[:size], words[size:]),
        ):
            if matched := _match_states(states, " ".join(candidate)):
                return matched, _strip_filler(rest)
    return None


def _in_states(level: LevelDef, state_ids: list[uuid.UUID]) -> ColumnElement[bool]:
    column = col(State.id) if level.name == "state" else level.parents["state_id"]
    return column.in_(state_ids)


async def _run(
    db: AsyncSession, geo: GeoScope, name: str, statement: Select[Any]
) -> list[dict[str, Any]]:
    visible = LEVELS[name].visible(geo)
    if visible is not None:
        statement = statement.where(visible)
    return [node_payload(name, dict(row)) for row in (await db.execute(statement)).mappings()]


def _active(level: LevelDef, framework: GeographicFramework) -> Select[Any]:
    return _node_select(level).where(
        col(level.model.framework_id) == framework.id, col(level.model.is_active).is_(True)
    )


async def _by_number(
    db: AsyncSession,
    geo: GeoScope,
    framework: GeographicFramework,
    names: list[str],
    number: int,
    *,
    state_code: int | None = None,
    state_ids: list[uuid.UUID] | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in names:
        if name not in _KEY_LEVELS:
            continue
        level = LEVELS[name]
        statement = _active(level, framework).where(level.code == number)
        if state_code is not None:
            statement = statement.where(col(State.state_code) == state_code)
        if state_ids is not None:
            statement = statement.where(_in_states(level, state_ids))
        statement = statement.order_by(col(State.state_code)).limit(limit)
        results.extend(await _run(db, geo, name, statement))
    return results


async def _by_name(
    db: AsyncSession,
    geo: GeoScope,
    framework: GeographicFramework,
    names: list[str],
    term: str,
    *,
    state_ids: list[uuid.UUID] | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in names:
        level = LEVELS[name]
        if level.label is None:
            continue
        normalized = func.f_unaccent(func.lower(level.label))
        statement = _active(level, framework).where(normalized.ilike(f"%{_normalize(term)}%"))
        if state_ids is not None:
            statement = statement.where(_in_states(level, state_ids))
        statement = statement.order_by(
            func.similarity(normalized, term).desc(), col(level.model.id)
        ).limit(limit)
        results.extend(await _run(db, geo, name, statement))
    return results


async def _within_states(
    db: AsyncSession,
    geo: GeoScope,
    framework: GeographicFramework,
    names: list[str],
    state_ids: list[uuid.UUID],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Every node of the levels inside the states, for queries that only name a state."""
    results: list[dict[str, Any]] = []
    for name in names:
        if name == "state":
            continue
        level = LEVELS[name]
        order = level.label if level.label is not None else level.code
        statement = (
            _active(level, framework)
            .where(_in_states(level, state_ids))
            .order_by(col(State.state_code), order, col(level.model.id))
            .limit(limit)
        )
        results.extend(await _run(db, geo, name, statement))
    return results


def _unique(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[uuid.UUID] = set()
    unique = []
    for item in results:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique[:limit]


async def search(
    db: AsyncSession,
    geo: GeoScope,
    query: str,
    *,
    levels: list[str] | None,
    limit: int,
    state_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Geography search (D-79). Understands, in this order:

    - INE keys: '09-0123', '9 123', '090123' (state + number) or a bare number ('338').
    - A number plus a state name, with optional level words: '338 aguascalientes',
      'distrito 3 jalisco', 'jalisco df 3'.
    - A name plus a state: 'centro aguascalientes' (colonias called Centro in that state).
    - Only a state: 'jalisco' finds the state and, for the levels asked for, what is inside it.
    - Otherwise an accent-insensitive name (municipalities, localities, colonias, states).

    `state_id` keeps every result inside one state (e.g. an address whose state is chosen).
    """
    framework = await active_framework(db)
    wanted = list(levels or [])
    within = [state_id] if state_id else None

    def narrow(state_ids: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if within is None or state_ids is None:
            return state_ids if state_ids is not None else within
        return [item for item in state_ids if item in within]

    async def by_number(
        names: list[str],
        number: int,
        state_code: int | None = None,
        state_ids: list[uuid.UUID] | None = None,
    ) -> list[dict[str, Any]]:
        found = await _by_number(
            db,
            geo,
            framework,
            names,
            number,
            state_code=state_code,
            state_ids=narrow(state_ids),
            limit=limit,
        )
        return _unique(found, limit)

    if match := _KEY.match(query):
        return await by_number(
            wanted or list(_KEY_LEVELS), int(match.group(2)), state_code=int(match.group(1))
        )
    if match := _COMPACT.match(query):
        default = ["section"] if len(match.group(2)) == 4 else ["municipality"]
        return await by_number(
            wanted or default, int(match.group(2)), state_code=int(match.group(1))
        )
    if match := _NUMBER.match(query):
        return await by_number(wanted or list(_KEY_LEVELS), int(match.group(1)))

    words = _fold(query).split()
    numbers = [word for word in words if word.isdigit()]
    states = await _states(db, framework)
    if len(numbers) == 1 and len(numbers[0]) <= 4:
        # "338 aguascalientes", "distrito 3 jalisco": a number inside the named state(s).
        implied = [level for word in words if word in _LEVEL_WORDS for level in _LEVEL_WORDS[word]]
        text = _strip_filler(
            [word for word in words if not word.isdigit() and word not in _LEVEL_WORDS]
        )
        state_ids = _match_states(states, " ".join(text)) if text else None
        if not text or state_ids:
            names = wanted or list(dict.fromkeys(implied)) or list(_KEY_LEVELS)
            return await by_number(names, int(numbers[0]), state_ids=state_ids)
        # Not a state: the digits are part of a name ("18 de marzo").

    term = " ".join(words)
    if len(term) < 3:
        raise BadRequestError("Escribe al menos 3 caracteres o una clave (p. ej. 09-0123).")
    names = wanted or list(_NAMED_LEVELS)
    results: list[dict[str, Any]] = []
    if split := _split_state(states, words):
        state_ids, rest = split
        if rest:
            results += await _by_name(
                db, geo, framework, names, " ".join(rest), state_ids=narrow(state_ids), limit=limit
            )
        else:
            results += await _by_name(
                db, geo, framework, names, term, state_ids=within, limit=limit
            )
            inside = narrow(state_ids)
            if wanted and inside:
                results += await _within_states(db, geo, framework, wanted, inside, limit=limit)
            return _unique(results, limit)
    results += await _by_name(db, geo, framework, names, term, state_ids=within, limit=limit)
    return _unique(results, limit)


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
    # The bbox filter stays on `geom` (its GiST index); only the emitted geometry changes (D-80).
    geometry = tile_geometry(table, z)
    sql = f"""
        WITH bounds AS (
          SELECT ST_TileEnvelope(:z, :x, :y) AS env,
                 ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => 0.015625), 4326) AS env4326
        ), features AS (
          SELECT {node} AS id, {code} AS code, {name} AS name,
                 ST_AsMVTGeom(ST_Transform({geometry}, 3857), bounds.env, 4096, 64, true) AS geom
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
