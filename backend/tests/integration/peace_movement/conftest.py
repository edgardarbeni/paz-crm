"""Fixtures for the Peace Movement: the synthetic BGD of tests/fixtures/bgd.py (one state, two
municipalities: 1 = sections 101, 102, 105, 106; 2 = 103, 104, 107, 108), the current notice of
the movement and helpers to enroll members through the API."""

import itertools
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.candidacies.conftest import (  # noqa: F401 - re-exported fixtures
    Geo,
    clean_candidacies,
    geo,
    make_curp,
    root,
    scoped,
)
from tests.integration.geography.conftest import (  # noqa: F401 - re-exported fixtures
    clean_geography,
    run_import,
)

__all__ = ["API", "Geo", "curp", "enroll", "person"]

API = "/api/v1/peace-movement"
_curps = itertools.count(1)


# National goals of migration 0014; `clean_geography` truncates states with CASCADE, which also
# empties the goals table, so they are seeded again after it.
SEEDED_GOALS = {
    "pacifier": (1, None),
    "peace_promoter": (10, None),
    "peace_messenger": (50, None),
    "peace_builder": (100, None),
    "peace_ambassador": (500, 5),
}


@pytest.fixture(autouse=True)
async def clean_peace_movement(
    owner_engine: AsyncEngine,
    clean_geography: None,  # noqa: F811 - runs first
    clean_candidacies: None,  # noqa: F811
) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE peace_movement.members, peace_movement.zone_coordinators, "
                "peace_movement.network_changes, peace_movement.level_goals, "
                "peace_movement.house_goals, people.privacy_notices CASCADE"
            )
        )
        for code, (recruit_goal, house_goal) in SEEDED_GOALS.items():
            await connection.execute(
                text(
                    "INSERT INTO peace_movement.level_goals (level_id, recruit_goal, house_goal, "
                    "valid_from) SELECT id, :recruit, :house, DATE '2026-01-01' "
                    "FROM peace_movement.participation_levels WHERE code = :code"
                ),
                {"code": code, "recruit": recruit_goal, "house": house_goal},
            )
        await connection.execute(
            text(
                "INSERT INTO peace_movement.house_goals (member_goal, valid_from) "
                "VALUES (100, DATE '2026-01-01')"
            )
        )
        await connection.execute(
            text(
                "UPDATE peace_movement.settings SET traffic_light_yellow_pct = 50, "
                "traffic_light_green_pct = 100, depth_alert_threshold = 50"
            )
        )


@pytest.fixture
async def notice(client: AsyncClient, root: dict[str, str]) -> dict[str, Any]:  # noqa: F811
    response = await client.post(
        "/api/v1/people/privacy-notices",
        headers=root,
        json={
            "code": "peace_movement",
            "version": "2026-10",
            "title": "Aviso de privacidad del Movimiento de Paz (ejemplo)",
            "body": "Texto de ejemplo del aviso del Movimiento de Paz, pendiente de jurídico.",
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


@pytest.fixture
async def levels(client: AsyncClient, root: dict[str, str]) -> dict[str, str]:  # noqa: F811
    listed = (await client.get(f"{API}/levels", headers=root)).json()
    return {level["code"]: level["id"] for level in listed}


def curp() -> str:
    """A structurally valid CURP: men born in Aguascalientes in January 1990."""
    n = next(_curps)
    return make_curp(
        f"LODA9001{(n % 28) + 1:02d}HASPZN{'0123456789ABCDEFGHJKLMNPRSTUVWXYZ'[n // 28]}"
    )


def person(section: str, *, name: str = "Juan", with_curp: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "given_names": name,
        "paternal_surname": "López",
        "maternal_surname": "Díaz",
        "address": {"street": "Calle de la Paz 1", "section_id": section},
        "contacts": [{"contact_type": "mobile", "value": "4491234567"}],
    }
    if with_curp:
        body["curp"] = curp()
    return body


async def enroll(
    client: AsyncClient,
    headers: dict[str, str],
    levels: dict[str, str],
    section: str,
    *,
    recruiter: str | None = None,
    level: str = "pacifier",
    expect: int = 201,
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "person": person(section),
        "level_id": levels[level],
        "consent": {"channel": "panel"},
        **extra,
    }
    if recruiter:
        body["recruiter_member_id"] = recruiter
        body.setdefault("origin", "recruiter")
    else:
        body.setdefault("origin", "structure")
    response = await client.post(f"{API}/members", headers=headers, json=body)
    assert response.status_code == expect, response.text
    result: dict[str, Any] = response.json()
    return result
