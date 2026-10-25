import asyncio

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.conftest import BACKEND_DIR, Database, migrate


async def test_core_objects_exist(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        extensions = set(
            (await connection.execute(text("SELECT extname FROM pg_extension"))).scalars()
        )
        schemas = set(
            (await connection.execute(text("SELECT nspname FROM pg_namespace"))).scalars()
        )
        version = (await connection.execute(text("SHOW server_version_num"))).scalar_one()
        uuid_v7 = (await connection.execute(text("SELECT uuid_extract_version(uuidv7())"))).scalar()
        unaccented = (await connection.execute(text("SELECT f_unaccent('Ñuñoa Álvaro')"))).scalar()
        postgis = (await connection.execute(text("SELECT postgis_lib_version()"))).scalar_one()

    assert {"postgis", "pg_trgm", "unaccent", "citext"} <= extensions
    assert {"identity", "geography", "people", "candidacies", "audit"} <= schemas
    assert int(version) >= 180000
    assert uuid_v7 == 7
    assert unaccented == "Nunoa Alvaro"
    assert postgis.startswith("3.")


async def test_migrations_roundtrip(database: Database, fresh_database: str) -> None:
    url = database.owner_url(fresh_database)
    await asyncio.to_thread(migrate, url, "base", downgrade=True)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            remaining = (
                await connection.execute(
                    text("SELECT count(*) FROM pg_namespace WHERE nspname IN ('audit','identity')")
                )
            ).scalar_one()
        assert remaining == 0
        await asyncio.to_thread(migrate, url, "head")
        async with engine.connect() as connection:
            head = (
                await connection.execute(text("SELECT version_num FROM public.alembic_version"))
            ).scalar_one()
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        assert head == ScriptDirectory.from_config(config).get_current_head()
    finally:
        await engine.dispose()
