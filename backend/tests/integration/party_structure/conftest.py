"""Fixtures for the party structure. Geography cleanup truncates with CASCADE, which also
empties `party_structure.bodies` (FKs to the framework and its nodes), so the national and state
bodies of migration 0019 are seeded again after it. Catalog rows created by tests use codes that
start with `test_`."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.candidacies.conftest import (  # noqa: F401 - re-exported fixtures
    Geo,
    clean_candidacies,
    geo,
    root,
    scoped,
)
from tests.integration.geography.conftest import (  # noqa: F401 - re-exported fixtures
    clean_geography,
    run_import,
)

API = "/api/v1/party-structure"

__all__ = ["API", "Geo"]


@pytest.fixture(autouse=True)
async def clean_party_structure(
    owner_engine: AsyncEngine,
    clean_geography: None,  # noqa: F811 - runs first
) -> None:
    async with owner_engine.begin() as connection:
        for sql in (
            "DELETE FROM party_structure.bodies WHERE framework_id IS NOT NULL",
            "DELETE FROM party_structure.position_incompatibilities",
            "DELETE FROM party_structure.position_derivations d USING "
            "party_structure.position_types p WHERE p.id = d.position_type_id "
            "AND p.code LIKE 'test%'",
            "DELETE FROM party_structure.position_types p USING party_structure.body_types b "
            "WHERE b.id = p.body_type_id AND (p.code LIKE 'test%' OR b.code LIKE 'test%')",
            "DELETE FROM party_structure.body_types WHERE code LIKE 'test%'",
            "DELETE FROM party_structure.coordination_position_types WHERE code LIKE 'test%'",
        ):
            await connection.execute(text(sql))
        seeded = (
            await connection.execute(text("SELECT count(*) FROM party_structure.bodies"))
        ).scalar_one()
        if not seeded:
            await connection.execute(
                text(
                    "INSERT INTO party_structure.bodies (body_type_id) SELECT id "
                    "FROM party_structure.body_types WHERE territorial_level = 'national'"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO party_structure.bodies (body_type_id, state_code) "
                    "SELECT b.id, s.code FROM party_structure.body_types b, "
                    "generate_series(1, 32) s(code) WHERE b.territorial_level = 'state'"
                )
            )
