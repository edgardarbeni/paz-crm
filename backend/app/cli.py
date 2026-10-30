"""Operational CLI: ``uv run paz --help``."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.audit import ensure_partitions, verify_chain
from app.core.config import Settings, get_settings
from app.core.crypto.keys import generate_key
from app.core.errors import AppError
from app.core.jobs import exclusive_job

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

    async def run() -> list[str] | None:
        engine = create_async_engine(get_settings().async_migrations_database_url)
        try:
            async with exclusive_job(engine, "audit.ensure_partitions") as acquired:
                if not acquired:
                    return None
                async with engine.begin() as connection:
                    return await ensure_partitions(connection, months_ahead=months_ahead)
        finally:
            await engine.dispose()

    created = asyncio.run(run())
    if created is None:
        typer.echo("Otra ejecución está en curso; no se hizo nada.")
        return
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
        jwt_secret="contract-placeholder-secret-not-used-for-signing",  # noqa: S106
    )


users_cli = typer.Typer(help="Usuarios.", no_args_is_help=True)
cli.add_typer(users_cli, name="users")


@users_cli.command("create-superadmin")
def users_create_superadmin(
    email: Annotated[str, typer.Option(prompt=True, help="Correo del superadministrador.")],
    full_name: Annotated[str, typer.Option(prompt="Nombre completo")],
    password: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)],
) -> None:
    """Crea el primer superadministrador (activo; debe enrolar TOTP en su primer acceso)."""
    from app.modules.identity.bootstrap import create_superadmin  # noqa: PLC0415

    try:
        user_id = asyncio.run(create_superadmin(get_settings(), email, full_name, password))
    except AppError as exc:
        typer.echo(f"Error: {exc.detail or exc.title}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Superadministrador creado: {user_id}. Configurará TOTP al iniciar sesión.")


geo_cli = typer.Typer(help="Geografía electoral (importación del INE).", no_args_is_help=True)
cli.add_typer(geo_cli, name="geo")


@geo_cli.command("download")
def geo_download(
    state: Annotated[int, typer.Option(min=1, max=32, help="Clave de entidad (1-32).")],
    dest: Annotated[Path, typer.Option(help="Carpeta destino (no se versiona).")] = Path(
        "../data/ine"
    ),
    bgd: Annotated[
        bool, typer.Option("--bgd/--no-bgd", help="Descargar también la BGD (7z).")
    ] = True,
) -> None:
    """Descarga del INE la BGD y los catálogos de un estado, con manifiesto y hashes (D-16)."""
    from app.modules.geography.ine import download_state  # noqa: PLC0415

    manifest = asyncio.run(download_state(get_settings(), state, dest, include_bgd=bgd))
    for item in manifest.files:
        typer.echo(f"{item.kind:<14} {item.bytes:>12,} B  {item.path}")
    typer.echo(
        f"Corte BGD: {manifest.bgd_cutoff or '-'} · corte catálogos: {manifest.catalogs_cutoff}"
    )


@geo_cli.command("import")
def geo_import(
    source: Annotated[
        Path, typer.Argument(help="Carpeta del estado, carpeta padre o .7z de la BGD.")
    ],
    state: Annotated[int, typer.Option(min=1, max=32, help="Clave de entidad (1-32).")],
    framework: Annotated[
        str, typer.Option(help="Nombre del marco geográfico.")
    ] = "INE BGD dic-2025",
    cutoff: Annotated[str | None, typer.Option(help="Fecha de corte AAAA-MM-DD.")] = "2025-12-15",
    catalogs: Annotated[
        Path | None, typer.Option(help="Carpeta del estado creada por `paz geo download`.")
    ] = None,
    catalogs_cutoff: Annotated[str | None, typer.Option(help="Corte de los catálogos.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Valida y reporta sin guardar.")
    ] = False,
) -> None:
    """Importa (o recarga) un estado: upsert por llave natural que conserva los IDs (D-02)."""
    from datetime import date  # noqa: PLC0415

    from app.modules.geography.importer.run import ImportOptions, import_state  # noqa: PLC0415
    from app.modules.geography.ine import Manifest  # noqa: PLC0415

    settings = get_settings()
    manifest = Manifest.load(catalogs) if catalogs else None
    catalogs_folder = (
        catalogs / "catalogos" if catalogs and (catalogs / "catalogos").is_dir() else catalogs
    )
    options = ImportOptions(
        source=source,
        state_code=state,
        framework_name=framework,
        cutoff_date=date.fromisoformat(cutoff) if cutoff else None,
        catalogs=catalogs_folder,
        catalogs_cutoff=catalogs_cutoff or (manifest.catalogs_cutoff if manifest else None),
        dry_run=dry_run,
    )

    async def run() -> int:
        engine = create_async_engine(settings.async_migrations_database_url)
        try:
            report = await import_state(engine, settings, options)
        finally:
            await engine.dispose()
        typer.echo(
            json.dumps(
                {
                    "run_id": str(report.run_id),
                    "status": report.status.value,
                    "dry_run": report.dry_run,
                    "errors": report.errors,
                    "warnings": report.warnings,
                    "layers_missing": report.layers_missing,
                    "message": report.message,
                    "counts": report.counts,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if report.status.value == "succeeded" else 1

    raise typer.Exit(asyncio.run(run()))


@geo_cli.command("activate")
def geo_activate(
    framework: Annotated[str, typer.Option(help="Nombre del marco a activar.")],
) -> None:
    """Activa un marco y remapea los alcances de los usuarios por llave natural (D-41)."""
    from app.modules.geography.frameworks import activate_framework  # noqa: PLC0415

    async def run() -> None:
        engine = create_async_engine(get_settings().async_migrations_database_url)
        try:
            async with engine.begin() as connection:
                report = await activate_framework(connection, name=framework)
        finally:
            await engine.dispose()
        typer.echo(f"Marco activo: {report.framework_id} (antes: {report.previous_framework_id})")
        typer.echo(f"Alcances remapeados: {report.remapped}")
        typer.echo(f"Alcances eliminados (sin equivalente): {report.removed}")
        typer.echo(f"Concesiones recalculadas: {report.grants_rebuilt}")
        for module, counts in report.modules.items():
            typer.echo(f"{module}: {counts}")

    asyncio.run(run())


@geo_cli.command("generalize")
def geo_generalize(
    framework: Annotated[
        str | None, typer.Option(help="Nombre del marco (por defecto, el activo).")
    ] = None,
) -> None:
    """Calcula las geometrías simplificadas de las teselas de zoom bajo sin reimportar (D-80)."""
    from app.modules.geography.generalize import generalize  # noqa: PLC0415

    async def run() -> int:
        engine = create_async_engine(get_settings().async_migrations_database_url)
        try:
            async with engine.begin() as connection:
                framework_id = (
                    await connection.execute(
                        text(
                            "SELECT id FROM geography.geographic_frameworks"
                            " WHERE deleted_at IS NULL"
                            " AND (name = :name OR (CAST(:name AS text) IS NULL AND is_active))"
                        ),
                        {"name": framework},
                    )
                ).scalar_one_or_none()
                if framework_id is None:
                    typer.echo("Error: no existe el marco indicado ni hay uno activo.", err=True)
                    raise typer.Exit(1)
                return await generalize(connection, framework_id=framework_id)
        finally:
            await engine.dispose()

    typer.echo(f"Geometrías generalizadas escritas: {asyncio.run(run())}")


people_cli = typer.Typer(help="Personas (datos personales).", no_args_is_help=True)
cli.add_typer(people_cli, name="people")


@people_cli.command("purge")
def people_purge() -> None:
    """Anonimiza a las personas dadas de baja cuyo plazo de retención venció (tarea programada)."""
    from app.core.db.session import build_engine, build_sessionmaker  # noqa: PLC0415
    from app.modules.people.service import purge_due  # noqa: PLC0415

    async def run() -> int | None:
        engine = build_engine(get_settings())
        try:
            async with exclusive_job(engine, "people.purge") as acquired:
                if not acquired:
                    return None
                async with build_sessionmaker(engine)() as db:
                    return await purge_due(db)
        finally:
            await engine.dispose()

    purged = asyncio.run(run())
    if purged is None:
        typer.echo("Otra ejecución está en curso; no se hizo nada.")
        return
    typer.echo(f"Personas anonimizadas: {purged}")


SAMPLE_NOTICES = {
    "peace_movement": (
        "Aviso de privacidad del Movimiento de Paz (EJEMPLO, no válido)",
        "TEXTO DE EJEMPLO PARA DESARROLLO. Este no es el aviso de privacidad del Movimiento de "
        "Paz: el texto definitivo y la forma de recabar el consentimiento expreso dependen de la "
        "revisión jurídica (D-92). No lo uses fuera de desarrollo.",
    ),
}


@people_cli.command("sample-notice")
def people_sample_notice(
    code: Annotated[str, typer.Option(help="Código del aviso.")] = "peace_movement",
) -> None:
    """Publica un aviso de privacidad de EJEMPLO (solo desarrollo y pruebas)."""
    from app.core.db.session import build_engine, build_sessionmaker  # noqa: PLC0415
    from app.modules.people.service import current_notice, publish_notice  # noqa: PLC0415

    settings = get_settings()
    if settings.environment.value in {"staging", "production"}:
        typer.echo("El aviso de ejemplo solo se publica en desarrollo o pruebas.", err=True)
        raise typer.Exit(1)
    if code not in SAMPLE_NOTICES:
        typer.echo(f"No hay texto de ejemplo para «{code}».", err=True)
        raise typer.Exit(1)
    title, body = SAMPLE_NOTICES[code]

    async def run() -> str:
        engine = build_engine(settings)
        try:
            async with build_sessionmaker(engine)() as db:
                if await current_notice(db, code) is not None:
                    return "Ya hay un aviso vigente; no se publicó el de ejemplo."
                await publish_notice(
                    db, code=code, version="ejemplo", title=title, body=body, is_sample=True
                )
                return f"Aviso de ejemplo «{code}» publicado."
        finally:
            await engine.dispose()

    typer.echo(asyncio.run(run()))


storage_cli = typer.Typer(help="Almacenamiento de archivos (S3).", no_args_is_help=True)
cli.add_typer(storage_cli, name="storage")


@storage_cli.command("ensure-bucket")
def storage_ensure_bucket() -> None:
    """Crea el bucket configurado si no existe (desarrollo; en producción se aprovisiona)."""
    from app.core.storage import build_storage  # noqa: PLC0415

    storage = build_storage(get_settings())
    if storage is None:
        typer.echo("PAZ_STORAGE_ENDPOINT no está configurado; no se hizo nada.")
        return
    created = asyncio.run(storage.ensure_bucket())
    typer.echo(f"Bucket «{storage.bucket}» {'creado' if created else 'ya existía'}.")


@keys_cli.command("generate")
def keys_generate() -> None:
    """Genera una llave aleatoria de 32 bytes en base64 (para .env)."""
    typer.echo(generate_key())


def mount_module_clis() -> None:
    """Adds the commands each module declares in `module.py` (`ModuleSpec.cli`)."""
    from app.core.modules import module_clis  # noqa: PLC0415

    mounted = {group.name for group in cli.registered_groups}
    for name, app in module_clis():
        if name not in mounted:
            cli.add_typer(app, name=name)


def main() -> None:
    from app.core.modules import setup_modules  # noqa: PLC0415

    setup_modules()
    mount_module_clis()
    cli()
