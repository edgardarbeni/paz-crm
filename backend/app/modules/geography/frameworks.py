"""Framework activation (D-01, D-41 point 7).

Activating a framework moves every grant scope to the equivalent node of the new framework by
natural key (state code + municipality / district / section number, region number). Scopes
whose node no longer exists are removed and reported. `user_grant_sections` is rebuilt.
The geography of personal addresses is remapped the same way; nodes without an equivalent are
cleared (the address itself is kept) and reported.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.audit import record_audit
from app.core.errors import BadRequestError, NotFoundError
from app.modules.identity.services.scopes import rebuild_all

# scope column → (geography table, natural-key join between old node `o` and new node `n`)
_REMAP: dict[str, tuple[str, str]] = {
    "electoral_region_id": ("electoral_regions", "n.region_number = o.region_number"),
    "state_id": ("states", "n.state_code = o.state_code"),
    "federal_district_id": (
        "federal_districts",
        "n.district_number = o.district_number AND ns.state_code = os.state_code",
    ),
    "local_district_id": (
        "local_districts",
        "n.district_number = o.district_number AND ns.state_code = os.state_code",
    ),
    "municipality_id": (
        "municipalities",
        "n.municipality_code = o.municipality_code AND ns.state_code = os.state_code",
    ),
    "section_id": (
        "sections",
        "n.section_number = o.section_number AND ns.state_code = os.state_code",
    ),
}


_STATE_JOIN = (
    "JOIN geography.states os ON os.id = o.state_id JOIN geography.states ns ON ns.id = n.state_id"
)


def _mapping_sql(table: str, natural_key: str) -> str:
    state_join = "" if table in {"states", "electoral_regions"} else _STATE_JOIN
    return (
        f"SELECT o.id AS old_id, n.id AS new_id FROM geography.{table} o "
        f"JOIN geography.{table} n ON n.framework_id = :new AND n.is_active "
        f"{state_join} WHERE {natural_key}"
    )


# person_addresses column → (geography table, old→new mapping query)
_ADDRESS_REMAP: dict[str, tuple[str, str]] = {
    **{
        column: (table, _mapping_sql(table, key))
        for column, (table, key) in _REMAP.items()
        if column in {"state_id", "municipality_id", "section_id"}
    },
    "locality_id": (
        "localities",
        "SELECT o.id AS old_id, n.id AS new_id FROM geography.localities o "
        "JOIN geography.municipalities om ON om.id = o.municipality_id "
        "JOIN geography.states os ON os.id = om.state_id "
        "JOIN geography.localities n ON n.framework_id = :new AND n.is_active "
        "JOIN geography.municipalities nm ON nm.id = n.municipality_id "
        "JOIN geography.states ns ON ns.id = nm.state_id "
        "WHERE n.locality_code = o.locality_code AND nm.municipality_code = om.municipality_code "
        "AND ns.state_code = os.state_code",
    ),
    "neighborhood_id": (
        "neighborhoods",
        _mapping_sql(
            "neighborhoods", "n.source_key = o.source_key AND ns.state_code = os.state_code"
        ),
    ),
}


@dataclass
class ActivationReport:
    framework_id: uuid.UUID
    previous_framework_id: uuid.UUID | None
    remapped: dict[str, int] = field(default_factory=dict)
    removed: dict[str, int] = field(default_factory=dict)
    grants_rebuilt: int = 0
    addresses_remapped: dict[str, int] = field(default_factory=dict)
    addresses_cleared: dict[str, int] = field(default_factory=dict)
    # What each module that registered a hook remapped or left pending (D-102).
    modules: dict[str, dict[str, int]] = field(default_factory=dict)


# Extension point: modules with data tied to geographic nodes remap it on activation
# (`ModuleSpec.setup`; geography never imports them). Hooks run inside the activation
# transaction, after the grant scopes and addresses and before the switch of active framework.
ActivationHook = Callable[[AsyncConnection, uuid.UUID, "ActivationReport"], Awaitable[None]]
_activation_hooks: list[ActivationHook] = []


def on_framework_activated(callback: ActivationHook) -> ActivationHook:
    if callback not in _activation_hooks:
        _activation_hooks.append(callback)
    return callback


def mapping_sql(table: str) -> str:
    """Old node → equivalent node of the framework `:new` by natural key (D-41 point 7)."""
    column = next(c for c, (t, _) in _REMAP.items() if t == table)
    return _mapping_sql(table, _REMAP[column][1])


async def activate_framework(connection: AsyncConnection, *, name: str) -> ActivationReport:
    new = (
        await connection.execute(
            text(
                "SELECT id, is_active FROM geography.geographic_frameworks WHERE name = :name AND deleted_at IS NULL"
            ),
            {"name": name},
        )
    ).one_or_none()
    if new is None:
        raise NotFoundError(f"No existe el marco {name!r}.")
    if new.is_active:
        raise BadRequestError(f"El marco {name!r} ya está activo.")
    has_data = (
        await connection.execute(
            text("SELECT 1 FROM geography.sections WHERE framework_id = :fw LIMIT 1"),
            {"fw": new.id},
        )
    ).first()
    if has_data is None:
        raise BadRequestError(
            "El marco no tiene secciones importadas; impórtalo antes de activarlo."
        )
    previous = (
        await connection.execute(
            text(
                "SELECT id FROM geography.geographic_frameworks WHERE is_active AND deleted_at IS NULL"
            )
        )
    ).scalar_one_or_none()
    report = ActivationReport(framework_id=new.id, previous_framework_id=previous)

    for column, (table, natural_key) in _REMAP.items():
        remapped = await connection.execute(
            text(
                f"UPDATE identity.user_grant_scopes us SET {column} = mapping.new_id, updated_at = now() "
                f"FROM ({_mapping_sql(table, natural_key)}) mapping "
                f"WHERE us.{column} = mapping.old_id"
            ),
            {"new": new.id},
        )
        report.remapped[column] = remapped.rowcount
        removed = await connection.execute(
            text(
                f"DELETE FROM identity.user_grant_scopes us USING geography.{table} o "
                f"WHERE us.{column} = o.id AND o.framework_id <> :new"
            ),
            {"new": new.id},
        )
        report.removed[column] = removed.rowcount

    await _remap_addresses(connection, new.id, report)
    for hook in _activation_hooks:
        await hook(connection, new.id, report)

    await connection.execute(
        text(
            "UPDATE geography.geographic_frameworks SET is_active = false, updated_at = now() WHERE is_active"
        )
    )
    await connection.execute(
        text(
            "UPDATE geography.geographic_frameworks SET is_active = true, activated_at = :now, "
            "updated_at = now() WHERE id = :id"
        ),
        {"id": new.id, "now": datetime.now(UTC)},
    )
    session = AsyncSession(bind=connection)
    report.grants_rebuilt = await rebuild_all(session)
    await session.flush()
    # Bulk rewrite: refresh planner statistics so scope EXISTS filters keep good plans.
    await connection.execute(text("ANALYZE identity.user_grant_sections"))
    await record_audit(
        connection,
        action="framework_activated",
        entity_table="geography.geographic_frameworks",
        entity_id=str(new.id),
        after={
            "previous_framework_id": str(previous) if previous else None,
            "remapped": report.remapped,
            "removed": report.removed,
            "addresses_remapped": report.addresses_remapped,
            "addresses_cleared": report.addresses_cleared,
            "modules": report.modules,
        },
    )
    return report


async def _remap_addresses(
    connection: AsyncConnection, new_id: uuid.UUID, report: ActivationReport
) -> None:
    for column, (table, mapping) in _ADDRESS_REMAP.items():
        remapped = await connection.execute(
            text(
                f"UPDATE people.person_addresses pa SET {column} = mapping.new_id, "
                f"updated_at = now() FROM ({mapping}) mapping WHERE pa.{column} = mapping.old_id"
            ),
            {"new": new_id},
        )
        report.addresses_remapped[column] = remapped.rowcount
        cleared = await connection.execute(
            text(
                f"UPDATE people.person_addresses pa SET {column} = NULL, updated_at = now() "
                f"FROM geography.{table} o WHERE pa.{column} = o.id AND o.framework_id <> :new"
            ),
            {"new": new_id},
        )
        report.addresses_cleared[column] = cleared.rowcount
