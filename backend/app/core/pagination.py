"""Keyset (cursor) pagination for large collections (CLAUDE.md: no unbounded SELECTs).

Usage in a repository::

    sort = parse_sort(params.sort, allowed={"name": Party.name}, tiebreaker=Party.id)
    page = await paginate(session, select(Party), sort=sort, limit=params.limit,
                          cursor=params.cursor)

The cursor is an opaque base64url token holding the sort-key values of the last row. The
last sort field must be unique (the primary key tiebreaker is always appended).
"""

import base64
import binascii
import datetime as dt
import decimal
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, NamedTuple

import orjson
from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class InvalidCursorError(BadRequestError):
    code = "invalid-cursor"
    title = "Cursor de paginación inválido"


class InvalidSortError(BadRequestError):
    code = "invalid-sort"
    title = "Criterio de ordenamiento inválido"


class SortField(NamedTuple):
    key: str
    column: ColumnElement[Any]
    descending: bool = False


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None = Field(
        default=None, description="Pasar en `cursor` para obtener la siguiente página."
    )
    has_more: bool


@dataclass(frozen=True, slots=True)
class PageParams:
    limit: int
    cursor: str | None
    sort: str | None


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    sort: Annotated[
        str | None,
        Query(
            max_length=200,
            description="Campos separados por coma; prefijo '-' para descendente.",
            examples=["-created_at,name"],
        ),
    ] = None,
) -> PageParams:
    return PageParams(limit=limit, cursor=cursor, sort=sort)


def parse_sort(
    raw: str | None,
    *,
    allowed: Mapping[str, ColumnElement[Any]],
    tiebreaker: ColumnElement[Any],
    default: str | None = None,
) -> list[SortField]:
    fields: list[SortField] = []
    for token in filter(None, (part.strip() for part in (raw or default or "").split(","))):
        descending = token.startswith("-")
        key = token.lstrip("-+")
        if key not in allowed:
            raise InvalidSortError(f"No se puede ordenar por '{key}'.")
        if any(field.key == key for field in fields):
            raise InvalidSortError(f"Campo de ordenamiento repetido: '{key}'.")
        fields.append(SortField(key, allowed[key], descending))
    fields.append(SortField("__id__", tiebreaker, fields[-1].descending if fields else False))
    return fields


# --- cursor encoding --------------------------------------------------------------------

_ENCODERS: dict[type, str] = {
    bool: "b",
    int: "i",
    str: "s",
    uuid.UUID: "u",
    dt.datetime: "dt",
    dt.date: "d",
    decimal.Decimal: "n",
}


def _encode_value(value: Any) -> list[Any]:
    if value is None:
        return ["0", None]
    tag = _ENCODERS.get(type(value))
    if tag is None:
        raise TypeError(f"Unsupported cursor value type: {type(value).__name__}")
    if tag in {"b", "i", "s"}:
        return [tag, value]
    return [tag, value.isoformat() if tag in {"dt", "d"} else str(value)]


def _decode_value(item: list[Any]) -> Any:
    tag, raw = item
    decoders: dict[str, Any] = {
        "0": lambda _: None,
        "b": bool,
        "i": int,
        "s": str,
        "u": uuid.UUID,
        "dt": dt.datetime.fromisoformat,
        "d": dt.date.fromisoformat,
        "n": decimal.Decimal,
    }
    return decoders[tag](raw)


def encode_cursor(values: Sequence[Any]) -> str:
    payload = orjson.dumps([_encode_value(value) for value in values])
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str, *, expected_fields: int) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        items = orjson.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(items, list) or len(items) != expected_fields:
            raise ValueError("cursor shape")
        return [_decode_value(item) for item in items]
    except (ValueError, KeyError, TypeError, binascii.Error, orjson.JSONDecodeError):
        raise InvalidCursorError("El cursor no corresponde a esta consulta.") from None


def _after(sort: Sequence[SortField], values: Sequence[Any]) -> ColumnElement[bool]:
    """Rows strictly after `values` in `sort` order (handles mixed directions)."""
    clauses = []
    for index, field in enumerate(sort):
        equal_prefix = [sort[i].column == values[i] for i in range(index)]
        beyond = field.column < values[index] if field.descending else field.column > values[index]
        clauses.append(and_(*equal_prefix, beyond))
    return or_(*clauses)


async def paginate[R](
    session: AsyncSession,
    statement: Select[tuple[R]],
    *,
    sort: Sequence[SortField],
    limit: int,
    cursor: str | None,
) -> CursorPage[R]:
    """`statement` must select a single entity or column; the sort keys are appended as extra
    labeled columns so the next cursor never depends on the item's attribute names."""
    if cursor:
        statement = statement.where(_after(sort, decode_cursor(cursor, expected_fields=len(sort))))
    order = [field.column.desc() if field.descending else field.column.asc() for field in sort]
    keyed = statement.add_columns(
        *(field.column.label(f"__sort_{index}") for index, field in enumerate(sort))
    )
    rows = list((await session.execute(keyed.order_by(*order).limit(limit + 1))).all())

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(list(rows[-1][1:])) if has_more and rows else None
    return CursorPage[R](items=[row[0] for row in rows], next_cursor=next_cursor, has_more=has_more)
