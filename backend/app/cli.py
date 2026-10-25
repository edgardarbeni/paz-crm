"""Operational CLI: ``uv run paz --help``."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.audit import ensure_partitions, verify_chain
from app.core.config import Settings, get_settings
from app.core.crypto.keys import generate_key

cli = typer.Typer(help="PAZOS — comandos de operación.", no_args_is_help=True)
audit_cli = typer.Typer(help="Bitácora de auditoría.", no_args_is_help=True)
openapi_cli = typer.Typer(help="Contrato OpenAPI.", no_args_is_help=True)
keys_cli = typer.Typer(help="Llaves de cifrado.", no_args_is_help=True)
cli.add_typer(audit_cli, name="audit")
cli.add_typer(openapi_cli, name="openapi")
cli.add_typer(keys_cli, name="keys")


@audit_cli.command("verify-chain")
def audit_verify_chain(
    from_seq: Annotated[int, typer.Option(help="Secuencia inicial.")] = 1,
) -> None:
    """Recalcula la cadena de hashes y reporta el primer eslabón roto."""

    async def run() -> int:
        engine = create_async_engine(get_settings().async_database_url)
        try:
            async with engine.connect() as connection:
                result = await verify_chain(connection, from_seq=from_seq)
        finally:
            await engine.dispose()
        if result.ok:
            typer.echo(f"OK: {result.checked} entradas verificadas.")
            return 0
        typer.echo(
            f"CADENA ROTA en la secuencia {result.first_broken_seq} "
            f"({result.checked} entradas válidas antes).",
            err=True,
        )
        return 1

    raise typer.Exit(asyncio.run(run()))


@audit_cli.command("ensure-partitions")
def audit_ensure_partitions(
    months_ahead: Annotated[int, typer.Option(min=1, max=24)] = 3,
) -> None:
    """Crea las particiones mensuales faltantes (requiere el rol dueño; usar en cron)."""

    async def run() -> list[str]:
        engine = create_async_engine(get_settings().async_migrations_database_url)
        try:
            async with engine.begin() as connection:
                return await ensure_partitions(connection, months_ahead=months_ahead)
        finally:
            await engine.dispose()

    created = asyncio.run(run())
    typer.echo(f"Particiones creadas: {', '.join(created) if created else 'ninguna'}")


@openapi_cli.command("export")
def openapi_export(
    output: Annotated[Path, typer.Argument(help="Archivo destino.")] = Path("openapi.json"),
) -> None:
    """Exporta el contrato OpenAPI sin levantar el servidor."""
    from app.main import create_app  # noqa: PLC0415 - avoid importing the app for other commands

    schema = create_app(_contract_settings()).openapi()
    output.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"OpenAPI escrito en {output}")


def _contract_settings() -> Settings:
    """Placeholder settings: exporting the contract never connects to any service."""
    placeholder_key = base64.b64encode(bytes(32)).decode()
    return Settings(
        api_docs_enabled=True,
        database_url="postgresql://contract:contract@localhost:5432/contract",
        redis_url="redis://localhost:6379/0",
        encryption_keys=f"1:{placeholder_key}",
        encryption_active_key_version=1,
        blind_index_key=placeholder_key,
    )


@keys_cli.command("generate")
def keys_generate() -> None:
    """Genera una llave aleatoria de 32 bytes en base64 (para .env)."""
    typer.echo(generate_key())


def main() -> None:
    cli()
