"""Fixtures for people and candidacies: the synthetic BGD (tests/fixtures/bgd.py) loaded as the
active framework, a superadmin token, scoped users and helpers.

Synthetic geography: sections 101-108 in a 4x2 grid. Municipality 1 = 101, 102, 105, 106;
municipality 2 = 103, 104, 107, 108. Local district 1 = columns 0-2, local district 2 = 104,
108. Federal district 1 = 101-104, federal district 2 = 105-108.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.people import curp
from tests.integration.conftest import Account, UserFactory, set_scopes, token_for
from tests.integration.geography.conftest import (  # noqa: F401 - re-exported fixtures
    Importer,
    clean_geography,
    rows,
    run_import,
    scalar,
)

SEEDED_OFFICES = (
    "municipal_president", "syndic", "councilor_mr", "councilor_rp", "mayor", "council_member",
    "local_deputy_mr", "local_deputy_rp", "governor", "federal_deputy_mr", "federal_deputy_rp",
    "senator_mr", "senator_rp", "president",
)  # fmt: skip


@pytest.fixture(autouse=True)
async def clean_candidacies(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE people.persons, candidacies.electoral_processes CASCADE")
        )
        await connection.execute(text("DELETE FROM candidacies.parties WHERE NOT is_own_party"))
        await connection.execute(
            text("DELETE FROM candidacies.office_types WHERE NOT (code = ANY(:codes))"),
            {"codes": list(SEEDED_OFFICES)},
        )


@dataclass(frozen=True)
class Geo:
    state: str
    region: str
    municipalities: dict[int, str]
    local_districts: dict[int, str]
    federal_districts: dict[int, str]
    sections: dict[int, str]


async def _ids(engine: AsyncEngine, sql: str) -> dict[int, str]:
    return {row["k"]: str(row["id"]) for row in await rows(engine, sql)}


@pytest.fixture
async def geo(run_import: Importer, owner_engine: AsyncEngine) -> Geo:  # noqa: F811
    await run_import()
    return Geo(
        state=str(await scalar(owner_engine, "SELECT id FROM geography.states")),
        region=str(await scalar(owner_engine, "SELECT id FROM geography.electoral_regions")),
        municipalities=await _ids(
            owner_engine, "SELECT municipality_code AS k, id FROM geography.municipalities"
        ),
        local_districts=await _ids(
            owner_engine, "SELECT district_number AS k, id FROM geography.local_districts"
        ),
        federal_districts=await _ids(
            owner_engine, "SELECT district_number AS k, id FROM geography.federal_districts"
        ),
        sections=await _ids(
            owner_engine, "SELECT section_number AS k, id FROM geography.sections WHERE is_active"
        ),
    )


@pytest.fixture
async def root(make_user: UserFactory, client: AsyncClient) -> dict[str, str]:
    return await token_for(client, await make_user(roles=("superadmin",), with_totp=True))


@pytest.fixture
def scoped(client: AsyncClient, make_user: UserFactory, root: dict[str, str]) -> Any:
    async def factory(
        roles: tuple[str, ...], scopes: list[dict[str, Any]] | None = None
    ) -> tuple[Account, dict[str, str]]:
        needs_totp = any(role in {"admin", "coordinator"} for role in roles)
        user = await make_user(roles=roles, with_totp=needs_totp)
        if scopes is not None:
            await set_scopes(client, root, user.id, scopes)
        return user, await token_for(client, user)

    return factory


def make_curp(prefix: str) -> str:
    """A structurally valid CURP from its first 17 characters."""
    return prefix + curp.check_digit(prefix)


_counter = {"n": 0}


async def new_person(
    client: AsyncClient, headers: dict[str, str], *, sex: str = "M", **fields: Any
) -> dict[str, Any]:
    _counter["n"] += 1
    body = {
        "given_names": f"Persona {_counter['n']}",
        "paternal_surname": "Prueba",
        "sex": sex,
        **fields,
    }
    response = await client.post("/api/v1/people", headers=headers, json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result
