"""Framework activation (D-01, D-41 point 7).

Activating a framework moves every user scope to the equivalent node of the new framework by
natural key (state code + municipality / district / section number, region number). Scopes
whose node no longer exists are removed and reported. `user_scope_sections` is rebuilt.
Personal addresses (phase D) will be remapped here too.
"""

import uuid
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


@dataclass
class ActivationReport:
    framework_id: uuid.UUID
    previous_framework_id: uuid.UUID | None
    remapped: dict[str, int] = field(default_factory=dict)
    removed: dict[str, int] = field(default_factory=dict)
    users_rebuilt: int = 0


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
        state_join = (
            ""
            if table in {"states", "electoral_regions"}
            else "JOIN geography.states os ON os.id = o.state_id JOIN geography.states ns ON ns.id = n.state_id"
        )
        remapped = await connection.execute(
            text(
                f"""
                UPDATE identity.user_scopes us SET {column} = mapping.new_id, updated_at = now()
                FROM (
                  SELECT o.id AS old_id, n.id AS new_id
                  FROM geography.{table} o
                  JOIN geography.{table} n ON n.framework_id = :new AND n.is_active
                  {state_join}
                  WHERE {natural_key}
                ) mapping
                WHERE us.{column} = mapping.old_id
                """
            ),
            {"new": new.id},
        )
        report.remapped[column] = remapped.rowcount
        removed = await connection.execute(
            text(
                f"DELETE FROM identity.user_scopes us USING geography.{table} o "
                f"WHERE us.{column} = o.id AND o.framework_id <> :new"
            ),
            {"new": new.id},
        )
        report.removed[column] = removed.rowcount

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
    report.users_rebuilt = await rebuild_all(session)
    await session.flush()
    # Bulk rewrite: refresh planner statistics so scope EXISTS filters keep good plans.
    await connection.execute(text("ANALYZE identity.user_scope_sections"))
    await record_audit(
        connection,
        action="framework_activated",
        entity_table="geography.geographic_frameworks",
        entity_id=str(new.id),
        after={
            "previous_framework_id": str(previous) if previous else None,
            "remapped": report.remapped,
            "removed": report.removed,
        },
    )
    return report
