"""Integration fixtures: real PostgreSQL 18 + PostGIS and Redis via testcontainers.

The PostGIS image is our own (infra/db). It is built on demand when missing; CI builds it in a
previous step and passes PAZ_TEST_PG_IMAGE.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import docker
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.config import Settings
from app.main import create_app
from tests.support import make_settings, pg_image

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
OWNER, OWNER_PASSWORD = "paz_owner", "paz_owner"
APP_USER, APP_PASSWORD = "paz_app", "paz_app"
DB_NAME = "paz"


@dataclass(frozen=True)
class Database:
    host: str
    port: int

    def url(self, *, user: str, password: str, database: str = DB_NAME) -> str:
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{database}"

    def owner_url(self, database: str = DB_NAME) -> str:
        return self.url(user=OWNER, password=OWNER_PASSWORD, database=database)

    def app_url(self, database: str = DB_NAME) -> str:
        return self.url(user=APP_USER, password=APP_PASSWORD, database=database)


def _ensure_image(tag: str) -> None:
    client = docker.from_env()
    try:
        client.images.get(tag)
    except docker.errors.ImageNotFound:
        client.images.build(path=str(REPO_DIR / "infra" / "db"), tag=tag, rm=True)


def migrate(url: str, revision: str = "head", *, downgrade: bool = False) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = url
    if downgrade:
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)


@pytest.fixture(scope="session")
def database() -> Iterator[Database]:
    image = pg_image()
    _ensure_image(image)
    container = PostgresContainer(
        image, username=OWNER, password=OWNER_PASSWORD, dbname=DB_NAME, driver=None
    )
    with container:
        db = Database(container.get_container_host_ip(), int(container.get_exposed_port(5432)))
        migrate(db.owner_url())
        yield db


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8-alpine") as container:
        host = container.get_container_host_ip()
        yield f"redis://{host}:{container.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def integration_settings(database: Database, redis_url: str) -> Settings:
    return make_settings(
        database_url=database.app_url().replace("+asyncpg", ""),
        migrations_database_url=database.owner_url().replace("+asyncpg", ""),
        redis_url=redis_url,
    )


@pytest.fixture(scope="session")
async def owner_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database.owner_url())
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def app_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database.app_url())
    yield engine
    await engine.dispose()


@pytest.fixture
async def fresh_database(database: Database, owner_engine: AsyncEngine) -> AsyncIterator[str]:
    """An isolated, fully migrated database for destructive tests. Yields its name."""
    name = f"paz_t_{uuid.uuid4().hex[:12]}"
    autocommit = owner_engine.execution_options(isolation_level="AUTOCOMMIT")
    async with autocommit.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
        await connection.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO {APP_USER}'))
    await asyncio.to_thread(migrate, database.owner_url(name))
    yield name
    async with autocommit.connect() as connection:
        await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(integration_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as http:
        yield http


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration/" in str(item.path).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
