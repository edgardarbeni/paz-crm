import datetime as dt
import decimal
import uuid

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table

from app.core.pagination import (
    InvalidCursorError,
    InvalidSortError,
    decode_cursor,
    encode_cursor,
    page_params,
    parse_sort,
)

items = Table(
    "items",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("name", String),
    Column("rank", Integer),
)


def test_cursor_roundtrip_all_supported_types() -> None:
    values = [
        None,
        True,
        42,
        "Álvaro Obregón",
        uuid.UUID("01900000-0000-7000-8000-000000000000"),
        dt.datetime(2026, 10, 24, 12, 30, tzinfo=dt.UTC),
        dt.date(2026, 10, 24),
        decimal.Decimal("12.50"),
    ]
    cursor = encode_cursor(values)
    assert "=" not in cursor
    assert decode_cursor(cursor, expected_fields=len(values)) == values


def test_encode_rejects_unsupported_types() -> None:
    with pytest.raises(TypeError, match="Unsupported"):
        encode_cursor([object()])


@pytest.mark.parametrize(
    "cursor", ["%%%", "bm90LWpzb24", encode_cursor([1]), encode_cursor([1, 2, 3])]
)
def test_invalid_cursors(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor, expected_fields=2)


def test_parse_sort_appends_tiebreaker_with_last_direction() -> None:
    sort = parse_sort(
        "-rank,name", allowed={"rank": items.c.rank, "name": items.c.name}, tiebreaker=items.c.id
    )
    assert [(f.key, f.descending) for f in sort] == [
        ("rank", True),
        ("name", False),
        ("__id__", False),
    ]
    default = parse_sort(
        None, allowed={"name": items.c.name}, tiebreaker=items.c.id, default="-name"
    )
    assert [(f.key, f.descending) for f in default] == [("name", True), ("__id__", True)]
    only_id = parse_sort(None, allowed={}, tiebreaker=items.c.id)
    assert [(f.key, f.descending) for f in only_id] == [("__id__", False)]


@pytest.mark.parametrize(("raw", "message"), [("password", "password"), ("name,-name", "repetido")])
def test_parse_sort_rejects_unknown_and_repeated(raw: str, message: str) -> None:
    with pytest.raises(InvalidSortError, match=message):
        parse_sort(raw, allowed={"name": items.c.name}, tiebreaker=items.c.id)


def test_page_params_defaults() -> None:
    params = page_params()
    assert (params.limit, params.cursor, params.sort) == (50, None, None)
