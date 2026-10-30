"""`paz peace-movement …`: scheduled aggregates and the load seed used to measure the module
with a million members (docs/modules/peace-movement.md, «Metas de rendimiento»)."""

import asyncio
import random
import secrets
import time
import uuid
from datetime import date, timedelta
from typing import Annotated, Any

import typer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.core.db.session import build_engine, build_sessionmaker
from app.core.jobs import exclusive_job
from app.modules.peace_movement import aggregates

app = typer.Typer(help="Movimiento de Paz.", no_args_is_help=True)

AGGREGATE_JOB = "peace_movement.aggregate"


@app.command("aggregate")
def aggregate(
    full: Annotated[bool, typer.Option(help="Recalcular toda la red (tarea nocturna).")] = False,
) -> None:
    """Aplica los cambios pendientes de la red a las estadísticas (tarea programada)."""

    async def run() -> aggregates.AggregationReport | None:
        engine = build_engine(get_settings())
        try:
            async with exclusive_job(engine, AGGREGATE_JOB) as acquired:
                if not acquired:
                    return None
                async with build_sessionmaker(engine)() as db:
                    if full:
                        return await aggregates.rebuild_all(db)
                    return await aggregates.drain(db)
        finally:
            await engine.dispose()

    started = time.perf_counter()
    report = asyncio.run(run())
    if report is None:
        typer.echo("Otra ejecución está en curso; no se hizo nada.")
        return
    typer.echo(
        f"Cambios: {report.changes} · nodos: {report.nodes} · días: {report.days} · "
        f"casas revisadas: {report.houses_checked} · {time.perf_counter() - started:.1f} s"
    )


# --- load seed (development only) -------------------------------------------------------------

LEVEL_WEIGHTS = {
    "pacifier": 70,
    "peace_promoter": 18,
    "peace_messenger": 7,
    "peace_builder": 4,
    "peace_ambassador": 1,
}


def plan_tree(count: int, chain: int, rng: random.Random) -> list[int]:
    """Parent index of each node (-1 for roots): a chain of `chain` nodes guarantees the
    depth, the rest hang from uniformly chosen earlier nodes (logarithmic typical depth)."""
    parents = [-1]
    for index in range(1, count):
        if index < chain:
            parents.append(index - 1)
        elif rng.random() < 0.001:
            parents.append(-1)
        else:
            parents.append(rng.randrange(index))
    return parents


async def _seed(engine: AsyncEngine, count: int, chain: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)  # noqa: S311 - load data, not security
    async with engine.connect() as connection:
        sections = (
            await connection.execute(
                text("SELECT id, state_id FROM geography.sections WHERE is_active")
            )
        ).all()
        levels: dict[str, uuid.UUID] = dict(
            (
                await connection.execute(
                    text("SELECT code, id FROM peace_movement.participation_levels")
                )
            ).all()
        )
        first_tree_id = (
            await connection.execute(
                text(
                    "SELECT setval('peace_movement.member_tree_ids', "
                    "nextval('peace_movement.member_tree_ids') + :n - 1) - :n + 1"
                ),
                {"n": count},
            )
        ).scalar_one()
        await connection.commit()
    if not sections:
        raise typer.BadParameter("No hay secciones activas: importa la geografía primero.")

    parents = plan_tree(count, chain, rng)
    codes = list(LEVEL_WEIGHTS)
    weights = list(LEVEL_WEIGHTS.values())
    person_rows: list[tuple[Any, ...]] = []
    member_rows: list[tuple[Any, ...]] = []
    ids: list[uuid.UUID] = []
    paths: list[str] = []
    today = date.today()
    for index, parent in enumerate(parents):
        person_id, member_id = uuid.uuid4(), uuid.uuid4()
        tree_id = first_tree_id + index
        path = f"{paths[parent]}.{tree_id}" if parent >= 0 else str(tree_id)
        ids.append(member_id)
        paths.append(path)
        section_id, state_id = sections[rng.randrange(len(sections))]
        person_rows.append((person_id, "Carga", f"Prueba {index}", True))
        member_rows.append(
            (
                member_id,
                person_id,
                today - timedelta(days=rng.randrange(730)),
                levels[rng.choices(codes, weights)[0]],
                ids[parent] if parent >= 0 else None,
                "recruiter" if parent >= 0 else "structure",
                "import",
                "active",
                secrets.token_urlsafe(12),
                tree_id,
                path,
                path.count("."),
                state_id,
                section_id,
            )
        )
    async with engine.connect() as connection:
        raw = await connection.get_raw_connection()
        driver: Any = raw.driver_connection
        await driver.copy_records_to_table(
            "persons",
            schema_name="people",
            columns=["id", "given_names", "paternal_surname", "curp_coherence_overridden"],
            records=person_rows,
        )
        # Binary COPY has no ltree encoder: load paths as text, then cast in one INSERT.
        await connection.execute(
            text(
                "CREATE TEMP TABLE seed_members (id uuid, person_id uuid, enrolled_on date, "
                "level_id uuid, recruited_by_member_id uuid, origin text, channel text, "
                "status text, referral_code text, tree_id bigint, path text, depth int, "
                "state_id uuid, section_id uuid) ON COMMIT DROP"
            )
        )
        await driver.copy_records_to_table("seed_members", records=member_rows)
        await connection.execute(
            text(
                "INSERT INTO peace_movement.members (id, person_id, enrolled_on, level_id, "
                "recruited_by_member_id, origin, channel, status, referral_code, tree_id, path, "
                "depth, state_id, section_id) SELECT id, person_id, enrolled_on, level_id, "
                "recruited_by_member_id, origin, channel, status, referral_code, tree_id, "
                "CAST(path AS ltree), depth, state_id, section_id FROM seed_members"
            )
        )
        await connection.execute(text("ANALYZE peace_movement.members"))
        await connection.commit()
    return {"members": count, "max_depth": max(p.count(".") for p in paths)}


@app.command("seed-load")
def seed_load(
    members: Annotated[int, typer.Option(min=10, max=5_000_000)] = 1_000_000,
    chain: Annotated[int, typer.Option(min=1, max=1000, help="Profundidad mínima.")] = 30,
    seed: Annotated[int, typer.Option(help="Semilla del generador.")] = 1,
) -> None:
    """Carga pacificadores sintéticos para medir el rendimiento (solo desarrollo y pruebas).

    Escribe con COPY, sin pasar por la bitácora: no se usa con datos reales."""
    settings = get_settings()
    if settings.environment.value in {"staging", "production"}:
        typer.echo("La carga sintética solo corre en desarrollo o pruebas.", err=True)
        raise typer.Exit(1)

    async def run() -> dict[str, Any]:
        # Owner role: COPY plus ANALYZE of the loaded tables.
        engine = create_async_engine(settings.async_migrations_database_url)
        try:
            return await _seed(engine, members, chain, seed)
        finally:
            await engine.dispose()

    started = time.perf_counter()
    result = asyncio.run(run())
    typer.echo(
        f"Pacificadores: {result['members']} · profundidad máxima: {result['max_depth']} · "
        f"{time.perf_counter() - started:.1f} s"
    )
