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
    user = await make_user()
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
    async with owner_engine.begin() as connection:
        for node in (section_101_a, section_108_a):
            await connection.execute(
                text(
                    "INSERT INTO identity.user_scopes (user_id, scope_level, section_id) "
                    "VALUES (:user, 'section', :node)"
                ),
                {"user": user.id, "node": node},
            )

    async with owner_engine.begin() as connection:
        report = await activate_framework(connection, name="Marco B")
    assert report.remapped["section_id"] == 1
    assert report.removed["section_id"] == 1  # section 108 does not exist in Marco B
    assert report.users_rebuilt == 1

    scopes = await rows(
        owner_engine,
        "SELECT s.section_number, f.name FROM identity.user_scopes us JOIN geography.sections s ON s.id = us.section_id "
        "JOIN geography.geographic_frameworks f ON f.id = s.framework_id WHERE us.user_id = :user",
        user=user.id,
    )
    assert scopes == [{"section_number": 101, "name": "Marco B"}]
    materialized = await scalar(
        owner_engine,
        "SELECT count(*) FROM identity.user_scope_sections uss JOIN geography.sections s ON s.id = uss.section_id "
        "JOIN geography.geographic_frameworks f ON f.id = s.framework_id WHERE f.name = 'Marco B' AND uss.user_id = :user",
        user=user.id,
    )
    assert materialized == 1
    active = await rows(
        owner_engine, "SELECT name FROM geography.geographic_frameworks WHERE is_active"
    )
    assert active == [{"name": "Marco B"}]


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
