"""Framework activation remaps user scopes by natural key (D-41 point 7) + migration drift."""

import asyncio
import os
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import BadRequestError, NotFoundError
from app.modules.geography.frameworks import activate_framework
from tests.conftest import BACKEND_DIR, Database
from tests.integration.conftest import UserFactory
from tests.integration.geography.conftest import Importer, rows, scalar


async def test_activation_remaps_scopes(
    run_import: Importer, make_user: UserFactory, owner_engine: AsyncEngine
) -> None:
    await run_import(framework="Marco A")
    await run_import(framework="Marco B", drop_section=108)
    user = await make_user(roles=("viewer",))
    section_101_a = await scalar(
        owner_engine,
        "SELECT s.id FROM geography.sections s JOIN geography.geographic_frameworks f ON f.id = s.framework_id "
        "WHERE f.name = 'Marco A' AND s.section_number = 101",
    )
    section_108_a = await scalar(
        owner_engine,
        "SELECT s.id FROM geography.sections s JOIN geography.geographic_frameworks f ON f.id = s.framework_id "
        "WHERE f.name = 'Marco A' AND s.section_number = 108",
    )
    grant = await scalar(
        owner_engine, "SELECT id FROM identity.user_grants WHERE user_id = :u", u=user.id
    )
    async with owner_engine.begin() as connection:
        for node in (section_101_a, section_108_a):
            await connection.execute(
                text(
                    "INSERT INTO identity.user_grant_scopes (grant_id, scope_level, section_id) "
                    "VALUES (:grant, 'section', :node)"
                ),
                {"grant": grant, "node": node},
            )

    async with owner_engine.begin() as connection:
        report = await activate_framework(connection, name="Marco B")
    assert report.remapped["section_id"] == 1
    assert report.removed["section_id"] == 1  # section 108 does not exist in Marco B
    assert report.grants_rebuilt == 1

    scopes = await rows(
        owner_engine,
        "SELECT s.section_number, f.name FROM identity.user_grant_scopes us JOIN geography.sections s ON s.id = us.section_id "
        "JOIN geography.geographic_frameworks f ON f.id = s.framework_id WHERE us.grant_id = :grant",
        grant=grant,
    )
    assert scopes == [{"section_number": 101, "name": "Marco B"}]
    materialized = await scalar(
        owner_engine,
        "SELECT count(*) FROM identity.user_grant_sections uss JOIN geography.sections s ON s.id = uss.section_id "
        "JOIN geography.geographic_frameworks f ON f.id = s.framework_id WHERE f.name = 'Marco B' AND uss.grant_id = :grant",
        grant=grant,
    )
    assert materialized == 1
    active = await rows(
        owner_engine, "SELECT name FROM geography.geographic_frameworks WHERE is_active"
    )
    assert active == [{"name": "Marco B"}]


async def test_activation_remaps_person_addresses(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    await run_import(framework="Marco A")
    await run_import(framework="Marco B", drop_section=108)

    def node(table: str, where: str) -> str:
        return (
            f"(SELECT x.id FROM geography.{table} x JOIN geography.geographic_frameworks f "
            f"ON f.id = x.framework_id WHERE f.name = 'Marco A' AND {where} LIMIT 1)"
        )

    async with owner_engine.begin() as connection:
        for section in (101, 108):
            person = (
                await connection.execute(
                    text(
                        "INSERT INTO people.persons (given_names, paternal_surname) "
                        "VALUES ('Remapeo', :s) RETURNING id"
                    ),
                    {"s": str(section)},
                )
            ).scalar_one()
            await connection.execute(
                text(
                    "INSERT INTO people.person_addresses (person_id, address_type, state_id, "
                    "municipality_id, section_id, locality_id, neighborhood_id, is_primary) "
                    f"SELECT :p, 'home', {node('states', 'true')}, s.municipality_id, s.id, "
                    f"{node('localities', 'x.municipality_id = s.municipality_id')}, "
                    f"{node('neighborhoods', 'x.municipality_id = s.municipality_id')}, true "
                    f"FROM geography.sections s WHERE s.id = {node('sections', f'x.section_number = {section}')}"
                ),
                {"p": person},
            )

    async with owner_engine.begin() as connection:
        report = await activate_framework(connection, name="Marco B")
    assert report.addresses_remapped["section_id"] == 1
    assert report.addresses_cleared["section_id"] == 1  # 108 is gone in Marco B
    assert report.addresses_remapped["municipality_id"] == 2
    assert report.addresses_remapped["state_id"] == 2
    assert report.addresses_remapped["locality_id"] + report.addresses_cleared["locality_id"] == 2

    stale = await scalar(
        owner_engine,
        "SELECT count(*) FROM people.person_addresses pa JOIN geography.geographic_frameworks f "
        "ON f.name = 'Marco A' WHERE f.id IN ("
        "(SELECT framework_id FROM geography.states WHERE id = pa.state_id), "
        "(SELECT framework_id FROM geography.municipalities WHERE id = pa.municipality_id), "
        "(SELECT framework_id FROM geography.sections WHERE id = pa.section_id), "
        "(SELECT framework_id FROM geography.localities WHERE id = pa.locality_id), "
        "(SELECT framework_id FROM geography.neighborhoods WHERE id = pa.neighborhood_id))",
    )
    assert stale == 0
    sections = await rows(
        owner_engine,
        "SELECT p.paternal_surname, s.section_number FROM people.person_addresses pa "
        "JOIN people.persons p ON p.id = pa.person_id "
        "LEFT JOIN geography.sections s ON s.id = pa.section_id ORDER BY 1",
    )
    assert sections == [
        {"paternal_surname": "101", "section_number": 101},
        {"paternal_surname": "108", "section_number": None},
    ]


async def test_activation_guards(run_import: Importer, owner_engine: AsyncEngine) -> None:
    await run_import(framework="Marco A")
    async with owner_engine.begin() as connection:
        with pytest.raises(BadRequestError, match="ya está activo"):
            await activate_framework(connection, name="Marco A")
        with pytest.raises(NotFoundError):
            await activate_framework(connection, name=f"inexistente-{uuid.uuid4()}")
        await connection.execute(
            text("INSERT INTO geography.geographic_frameworks (name) VALUES ('Vacío')")
        )
        with pytest.raises(BadRequestError, match="no tiene secciones"):
            await activate_framework(connection, name="Vacío")


async def test_models_and_migrations_do_not_drift(database: Database) -> None:
    """`alembic check` in a fresh process (test-only tables live in this process' metadata):
    autogenerate must find nothing to add, so hand-adjusted migrations match the models."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "check",
        cwd=BACKEND_DIR,
        env={**os.environ, "PAZ_MIGRATIONS_DATABASE_URL": database.owner_url()},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    assert process.returncode == 0, output.decode()
    assert "No new upgrade operations detected" in output.decode()
