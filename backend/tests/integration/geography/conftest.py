from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.modules.geography.importer.run import ImportOptions, ImportReport, import_state
from tests.fixtures.bgd import build_catalogs, build_state

FRAMEWORK = "INE prueba 2025"

Importer = Callable[..., Awaitable[ImportReport]]


@pytest.fixture(autouse=True)
async def clean_geography(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE geography.geographic_frameworks, geography.import_runs, "
                "geography.section_types, geography.federal_district_types, geography.block_statuses, "
                "geography.locality_types, geography.locality_head_types, geography.neighborhood_types "
                "CASCADE"
            )
        )


@pytest.fixture
def run_import(
    owner_engine: AsyncEngine, integration_settings: Settings, tmp_path: Path
) -> Importer:
    counter = {"n": 0}

    async def importer(
        *,
        framework: str = FRAMEWORK,
        catalogs: bool = True,
        dry_run: bool = False,
        source: Path | None = None,
        **variant: Any,
    ) -> ImportReport:
        counter["n"] += 1
        root = tmp_path / f"bgd{counter['n']}"
        if source is None:
            build_state(root, **variant)
            source = root
        if catalogs:
            build_catalogs(root)
        options = ImportOptions(
            source=source,
            state_code=1,
            framework_name=framework,
            cutoff_date=date(2025, 12, 15),
            catalogs=(root / "catalogos") if catalogs else None,
            catalogs_cutoff="19ENE2026" if catalogs else None,
            dry_run=dry_run,
            triggered_by="pytest",
        )
        return await import_state(owner_engine, integration_settings, options)

    return importer


async def scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as connection:
        return (await connection.execute(text(sql), params)).scalar()


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        return [dict(row) for row in (await connection.execute(text(sql), params)).mappings()]
