"""`paz party-structure` commands."""

import asyncio
from datetime import UTC, datetime

import typer

from app.core.config import get_settings
from app.core.db.session import build_engine, build_sessionmaker
from app.core.jobs import exclusive_job
from app.modules.party_structure.access import expire_due

app = typer.Typer(help="Estructura del partido.", no_args_is_help=True)


@app.command("expire")
def expire() -> None:
    """Termina los nombramientos cuyo periodo venció y retira su acceso (tarea diaria)."""

    async def run() -> int | None:
        engine = build_engine(get_settings())
        try:
            async with exclusive_job(engine, "party_structure.expire") as acquired:
                if not acquired:
                    return None
                async with build_sessionmaker(engine)() as db:
                    return await expire_due(db, datetime.now(UTC).date())
        finally:
            await engine.dispose()

    ended = asyncio.run(run())
    if ended is None:
        typer.echo("Otra ejecución está en curso; se omite.")
    else:
        typer.echo(f"Nombramientos vencidos terminados: {ended}")
