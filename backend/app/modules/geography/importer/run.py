"""Import orchestration for one state (D-18).

The data load runs in one transaction (rolled back in dry-run mode). The import run and its
issues are written through a separate connection, so they survive a dry run or a failure and
always explain what happened. Imports connect with the owner role (they create partitions).
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlmodel import col

from app.core.audit import record_audit
from app.core.config import Settings
from app.core.context import RequestContext, set_context
from app.core.logging import get_logger
from app.modules.geography.importer.catalogs import load_catalogs
from app.modules.geography.importer.layers import LOAD_ORDER, SPECS, Issue, Staged, stage
from app.modules.geography.importer.loader import Loader
from app.modules.geography.importer.source import BgdSource, SourceError, open_source
from app.modules.geography.models import (
    GeographicFramework,
    ImportIssue,
    ImportRun,
    ImportStatus,
)

logger = get_logger(__name__)

ISSUE_BATCH = 1000


@dataclass
class ImportOptions:
    source: Path
    state_code: int
    framework_name: str
    cutoff_date: date | None = None
    source_agreement: str | None = None
    catalogs: Path | None = None
    catalogs_cutoff: str | None = None
    dry_run: bool = False
    triggered_by: str = "paz-cli"


@dataclass
class ImportReport:
    run_id: uuid.UUID
    framework_id: uuid.UUID
    status: ImportStatus
    dry_run: bool
    counts: dict[str, Any] = field(default_factory=dict)
    errors: int = 0
    warnings: int = 0
    layers_missing: list[str] = field(default_factory=list)
    message: str | None = None


async def ensure_framework(
    connection: AsyncConnection,
    *,
    name: str,
    cutoff_date: date | None,
    source_agreement: str | None,
) -> uuid.UUID:
    """Gets or creates the framework (the first one becomes active, D-01) and its blocks
    partition (D-14)."""
    table = GeographicFramework.__table__  # type: ignore[attr-defined]
    found = (
        await connection.execute(
            select(table.c.id).where(table.c.name == name, table.c.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if found is None:
        any_active = (
            await connection.execute(select(table.c.id).where(table.c.is_active.is_(True)))
        ).first()
        found = (
            await connection.execute(
                insert(table)
                .values(
                    name=name,
                    cutoff_date=cutoff_date,
                    source_agreement=source_agreement,
                    is_active=any_active is None,
                    activated_at=datetime.now(UTC) if any_active is None else None,
                )
                .returning(table.c.id)
            )
        ).scalar_one()
    await connection.execute(text("SELECT geography.ensure_block_partition(:id)"), {"id": found})
    framework_id: uuid.UUID = found
    return framework_id


class RunJournal:
    """Writes the import run and its issues outside the data transaction."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.run_table = ImportRun.__table__  # type: ignore[attr-defined]
        self.issue_table = ImportIssue.__table__  # type: ignore[attr-defined]

    async def start(
        self, framework_id: uuid.UUID, options: ImportOptions, source_uri: str
    ) -> uuid.UUID:
        async with self.engine.begin() as connection:
            run_id: uuid.UUID = (
                await connection.execute(
                    insert(self.run_table)
                    .values(
                        framework_id=framework_id,
                        source_kind="bgd_shapefile",
                        state_code=options.state_code,
                        source_uri=source_uri,
                        dry_run=options.dry_run,
                        status=ImportStatus.RUNNING,
                        counts={},
                        layers_loaded=[],
                        layers_missing=[],
                        started_at=datetime.now(UTC),
                        triggered_by=options.triggered_by,
                    )
                    .returning(self.run_table.c.id)
                )
            ).scalar_one()
        return run_id

    async def finish(
        self, run_id: uuid.UUID, report: ImportReport, issues: list[Issue], **extra: Any
    ) -> None:
        async with self.engine.begin() as connection:
            for start in range(0, len(issues), ISSUE_BATCH):
                batch = issues[start : start + ISSUE_BATCH]
                await connection.execute(
                    insert(self.issue_table),
                    [
                        {
                            "import_run_id": run_id,
                            "layer": issue.layer,
                            "source_fid": issue.source_fid,
                            "natural_key": _jsonable(issue.natural_key),
                            "severity": issue.severity,
                            "code": issue.code,
                            "message": issue.message,
                        }
                        for issue in batch
                    ],
                )
            await connection.execute(
                update(self.run_table)
                .where(col(self.run_table.c.id) == run_id)
                .values(
                    status=report.status,
                    counts=report.counts,
                    error_count=report.errors,
                    warning_count=report.warnings,
                    layers_missing=report.layers_missing,
                    message=report.message,
                    finished_at=datetime.now(UTC),
                    **extra,
                )
            )
            await record_audit(
                connection,
                action="geo_import",
                entity_table="geography.import_runs",
                entity_id=str(run_id),
                after={
                    "status": report.status.value,
                    "dry_run": report.dry_run,
                    "state_code": extra.get("state_code"),
                    "errors": report.errors,
                    "warnings": report.warnings,
                },
            )


def _jsonable(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        key: (str(item) if isinstance(item, uuid.UUID) else item) for key, item in value.items()
    }


def _read_layers(source: BgdSource, state_code: int) -> tuple[dict[str, Staged], int, list[str]]:
    staged: dict[str, Staged] = {}
    missing: list[str] = []
    srids: set[int] = set()
    for name in LOAD_ORDER:
        spec = SPECS[name]
        if not source.has(name):
            if spec.required_layer:
                raise SourceError(f"Falta la capa obligatoria {name}.")
            missing.append(name)
            continue
        data = source.read(name)
        srids.add(data.srid)
        staged[name] = stage(spec, data, state_code=state_code)
    if len(srids) != 1:
        raise SourceError(f"Las capas usan sistemas de coordenadas distintos: {sorted(srids)}")
    return staged, srids.pop(), missing


async def import_state(
    engine: AsyncEngine, settings: Settings, options: ImportOptions
) -> ImportReport:
    set_context(
        RequestContext(
            request_id=f"geo-import-{uuid.uuid4().hex[:12]}", user_agent=options.triggered_by
        )
    )
    async with engine.begin() as connection:
        framework_id = await ensure_framework(
            connection,
            name=options.framework_name,
            cutoff_date=options.cutoff_date,
            source_agreement=options.source_agreement,
        )
    journal = RunJournal(engine)

    with open_source(options.source, state_code=options.state_code) as source:
        run_id = await journal.start(framework_id, options, source.uri)
        report = ImportReport(
            run_id=run_id,
            framework_id=framework_id,
            status=ImportStatus.FAILED,
            dry_run=options.dry_run,
        )
        issues: list[Issue] = []
        extra: dict[str, Any] = {"state_code": options.state_code}
        try:
            staged, srid, missing = _read_layers(source, options.state_code)
            report.layers_missing = missing
            extra.update(
                source_srid=srid,
                layers_loaded=[name for name in LOAD_ORDER if name in staged],
                file_sha256=source.sha256(list(staged)),
            )
            for name in missing:
                issues.append(
                    Issue(name, "warning", "missing_layer", "La capa no viene en la fuente.")
                )
            catalogs = load_catalogs(options.catalogs, cutoff=options.catalogs_cutoff)

            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    loader = Loader(
                        connection,
                        settings,
                        framework_id=framework_id,
                        run_id=run_id,
                        state_code=options.state_code,
                    )
                    timings: dict[str, float] = {}
                    steps: list[tuple[str, Callable[[], Awaitable[None]]]] = [
                        ("stage", lambda: loader.stage(staged, srid)),
                        ("states", loader.load_states),
                        ("municipalities", loader.load_municipalities),
                        ("districts", loader.load_districts),
                        ("sections", loader.load_sections),
                        ("localities", loader.load_localities),
                        ("blocks", loader.load_blocks),
                        ("neighborhoods", loader.load_neighborhoods),
                        ("derived", lambda: loader.derive(catalogs, staged)),
                    ]
                    for step, action in steps:
                        started = time.perf_counter()
                        await action()
                        timings[step] = round(time.perf_counter() - started, 2)
                    issues.extend(loader.result.issues)
                    report.counts = {
                        "tables": {
                            name: counts.as_dict() for name, counts in loader.result.counts.items()
                        },
                        "derived": loader.result.derived,
                        "timings_s": timings,
                    }
                    if options.dry_run:
                        await transaction.rollback()
                    else:
                        await transaction.commit()
                except BaseException:
                    await transaction.rollback()
                    raise
            report.status = ImportStatus.SUCCEEDED
            report.message = "Simulación: no se guardaron cambios." if options.dry_run else None
        except (SourceError, ValueError) as exc:
            report.message = str(exc)
            issues.append(Issue("SOURCE", "error", "import_failed", str(exc)))
        except Exception as exc:
            logger.exception("geo_import_failed", run_id=str(run_id))
            report.message = f"Error inesperado: {type(exc).__name__}: {exc}"
            issues.append(Issue("SOURCE", "error", "import_failed", report.message))
        report.errors = sum(1 for issue in issues if issue.severity == "error")
        report.warnings = sum(1 for issue in issues if issue.severity == "warning")
        await journal.finish(run_id, report, issues, **extra)
    return report
