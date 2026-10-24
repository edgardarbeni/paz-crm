from collections.abc import AsyncIterator
from operator import itemgetter
from typing import Any

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.pagination import SortField, paginate, parse_sort

metadata = MetaData(schema="identity")
items = Table(
    "pagination_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("rank", Integer, nullable=True),
)
ROWS: list[dict[str, Any]] = [
    {"id": i, "name": f"item-{i % 7}", "rank": i % 3} for i in range(1, 51)
]


@pytest.fixture(scope="module")
async def seeded(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    async with owner_engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.execute(insert(items), ROWS)
    yield
    async with owner_engine.begin() as connection:
        await connection.run_sync(metadata.drop_all)


async def _walk(engine: AsyncEngine, sort: list[SortField], limit: int) -> list[int]:
    collected: list[int] = []
    cursor = None
    async with AsyncSession(engine) as session:
        while True:
            page = await paginate(
                session, select(items.c.id), sort=sort, limit=limit, cursor=cursor
            )
            collected.extend(page.items)
            if not page.has_more:
                assert page.next_cursor is None
                return collected
            cursor = page.next_cursor


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize("raw_sort", [None, "-rank,name", "name,-rank", "-name"])
async def test_walks_every_row_once_in_order(
    owner_engine: AsyncEngine, raw_sort: str | None
) -> None:
    sort = parse_sort(
        raw_sort, allowed={"name": items.c.name, "rank": items.c.rank}, tiebreaker=items.c.id
    )
    collected = await _walk(owner_engine, sort, limit=7)

    # Reference order: stable multi-pass sort, last key first (handles mixed directions).
    expected_rows = list(ROWS)
    for field in reversed(sort):
        column = "id" if field.key == "__id__" else field.key
        expected_rows.sort(key=itemgetter(column), reverse=field.descending)
    assert collected == [int(row["id"]) for row in expected_rows]
