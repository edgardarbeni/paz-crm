"""Activating a geographic framework (phase 5, D-102 and D-105).

Inside the activation transaction (a `geography` hook):
- District and municipal committees and the territory of the coordinations move to the
  equivalent node by natural key.
- What has no equivalent is not deleted:
  - a committee keeps pointing to its old node, so it has no territory or scope in the new
    framework, and goes to the tray;
  - a coordination's lost nodes are retired (`removed_on`), and the coordination goes to the
    tray with the list.
- State bodies keep the INE state code and need nothing (D-107).
- The grants of the holders are remapped by `identity` like any other scope.

The tray is resolved by a national admin: reassign or dissolve a committee, accept or close a
coordination. Every way out ends current appointments through the ordinary path (revoking
access, D-109).
"""

import json
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlmodel import col

from app.core.audit import record_audit
from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.modules.geography.frameworks import ActivationReport, mapping_sql
from app.modules.identity.models import GrantOrigin, UserGrant
from app.modules.identity.services.access import Access
from app.modules.identity.services.grants import sync_scopes
from app.modules.identity.services.scopes import GeoScope, active_framework
from app.modules.party_structure import access as structure_access
from app.modules.party_structure import appointments, coordinations
from app.modules.party_structure.models import (
    Appointment,
    Body,
    DistrictKind,
    EndReason,
    IssueKind,
    Position,
    TerritoryIssue,
)

# committee node column → (geography table, readable label of an old node `o`)
_COMMITTEE_NODES = {
    "municipality_id": ("municipalities", "o.name"),
    "federal_district_id": ("federal_districts", "'Distrito federal ' || o.district_number"),
    "local_district_id": ("local_districts", "'Distrito local ' || o.district_number"),
}
# coordination territory table → (node column, geography table, label of an old node `o`)
_COORDINATION_NODES = {
    "coordination_federal_districts": (
        "federal_district_id",
        "federal_districts",
        "'Distrito federal ' || o.district_number",
    ),
    "coordination_local_districts": (
        "local_district_id",
        "local_districts",
        "'Distrito local ' || o.district_number",
    ),
    "coordination_sections": ("section_id", "sections", "'Sección ' || o.section_number"),
}


async def remap_structure(
    connection: AsyncConnection, new_id: uuid.UUID, report: ActivationReport
) -> None:
    """`geography` activation hook (registered in `hooks.py`)."""
    today = datetime.now(UTC).date()
    counts: dict[str, int] = {}
    params = {"new": new_id, "today": today}
    for column, (table, label) in _COMMITTEE_NODES.items():
        moved = await connection.execute(
            text(
                f"UPDATE party_structure.bodies b SET {column} = m.new_id, "  # noqa: S608
                "framework_id = :new, updated_at = now() "
                f"FROM ({mapping_sql(table)}) m WHERE b.{column} = m.old_id "
                "AND b.dissolved_on IS NULL AND b.deleted_at IS NULL"
            ),
            params,
        )
        counts[f"committees_{column}"] = moved.rowcount
        orphans = await connection.execute(
            text(
                "INSERT INTO party_structure.territory_issues "  # noqa: S608
                "(body_id, kind, framework_id, detected_on, lost) "
                "SELECT b.id, 'committee_without_territory', :new, :today, "
                f"jsonb_build_array(jsonb_build_object('id', o.id, 'label', {label})) "
                f"FROM party_structure.bodies b JOIN geography.{table} o ON o.id = b.{column} "
                "WHERE o.framework_id <> :new AND b.dissolved_on IS NULL AND b.deleted_at IS NULL"
            ),
            params,
        )
        counts["committees_without_territory"] = (
            counts.get("committees_without_territory", 0) + orphans.rowcount
        )
    for table, (column, geo_table, label) in _COORDINATION_NODES.items():
        moved = await connection.execute(
            text(
                f"UPDATE party_structure.{table} t SET {column} = m.new_id, "  # noqa: S608
                f"updated_at = now() FROM ({mapping_sql(geo_table)}) m "
                f"WHERE t.{column} = m.old_id AND t.removed_on IS NULL AND t.deleted_at IS NULL"
            ),
            params,
        )
        counts[f"coordination_{column}"] = moved.rowcount
        lost = f"""
            SELECT t.id, t.coordination_id, o.id AS node, {label} AS label
            FROM party_structure.{table} t JOIN geography.{geo_table} o ON o.id = t.{column}
            WHERE o.framework_id <> :new AND t.removed_on IS NULL AND t.deleted_at IS NULL
        """  # noqa: S608
        issues = await connection.execute(
            text(
                "INSERT INTO party_structure.territory_issues "  # noqa: S608
                "(body_id, kind, framework_id, detected_on, lost) "
                "SELECT l.coordination_id, 'coordination_nodes_removed', :new, :today, "
                "jsonb_agg(jsonb_build_object('id', l.node, 'label', l.label) ORDER BY l.label) "
                f"FROM ({lost}) l GROUP BY l.coordination_id"
            ),
            params,
        )
        counts["coordinations_with_lost_territory"] = (
            counts.get("coordinations_with_lost_territory", 0) + issues.rowcount
        )
        await connection.execute(
            text(
                f"UPDATE party_structure.{table} t SET removed_on = :today, "  # noqa: S608
                f"updated_at = now() WHERE t.id IN (SELECT id FROM ({lost}) l)"
            ),
            params,
        )
    await connection.execute(
        text(
            "UPDATE party_structure.bodies b SET framework_id = :new, updated_at = now() "
            "FROM party_structure.body_types t WHERE t.id = b.body_type_id "
            "AND t.coordination_kind IS NOT NULL AND b.dissolved_on IS NULL"
        ),
        params,
    )
    report.modules["party_structure"] = counts
    await record_audit(
        connection,
        action="framework_remapped",
        entity_table="party_structure.bodies",
        entity_id=str(new_id),
        after=json.loads(json.dumps(counts)),
    )


# --- the tray ---------------------------------------------------------------------------------


def ensure_national(geo: GeoScope) -> None:
    """D-102: a national admin resolves the tray (orphans have no territory to scope by)."""
    if not geo.unrestricted:
        raise ForbiddenError("La bandeja de territorio por resolver es del nivel nacional.")


async def issues(db: AsyncSession, *, include_resolved: bool) -> list[TerritoryIssue]:
    statement = select(TerritoryIssue).where(col(TerritoryIssue.deleted_at).is_(None))
    if not include_resolved:
        statement = statement.where(col(TerritoryIssue.resolved_at).is_(None))
    rows = await db.execute(statement.order_by(col(TerritoryIssue.detected_on).desc()))
    return list(rows.scalars())


async def _open_issue(db: AsyncSession, issue_id: uuid.UUID) -> TerritoryIssue:
    issue = await db.get(TerritoryIssue, issue_id)
    if issue is None or issue.deleted_at is not None:
        raise NotFoundError("Pendiente no encontrado.")
    if issue.resolved_at is not None:
        raise ConflictError("Ese pendiente ya se resolvió.")
    return issue


async def _end_current(db: AsyncSession, body_id: uuid.UUID, on: date, why: str) -> None:
    """Ends the body's current appointments and revokes their access (caller commits)."""
    rows = await db.execute(
        select(Appointment)
        .join(Position, col(Position.id) == col(Appointment.position_id))
        .where(
            col(Position.body_id) == body_id,
            col(Appointment.ended_on).is_(None),
            col(Appointment.deleted_at).is_(None),
        )
    )
    for appointment in rows.scalars():
        appointment.ended_on = max(on, appointment.starts_on)
        appointment.end_reason = EndReason.OTHER
        appointment.end_notes = why
        position = await db.get(Position, appointment.position_id)
        assert position is not None  # noqa: S101 - FK
        position.vacant_since = appointment.ended_on
        await structure_access.revoke_access(db, appointment)
    await db.flush()


def _close(issue: TerritoryIssue, user_id: uuid.UUID, resolution: str, notes: str | None) -> None:
    issue.resolved_at = datetime.now(UTC)
    issue.resolution = resolution
    issue.resolution_notes = notes
    issue.resolved_by_user_id = user_id


async def _sync_holders(db: AsyncSession, body: Body) -> None:
    """After a committee gets its node back, its holders' grants take it as scope."""
    seats = await appointments.seats_of(db, pk(body))
    for seat in seats:
        current = (await appointments.current_appointments(db, [pk(seat.position)])).get(
            pk(seat.position)
        )
        if current is None:
            continue
        grants = await db.execute(
            select(UserGrant).where(
                col(UserGrant.origin) == GrantOrigin.APPOINTMENT,
                col(UserGrant.source_id) == pk(current),
            )
        )
        for grant in grants.scalars():
            await sync_scopes(db, grant, await structure_access.seat_scopes(db, seat))


async def resolve(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    access: Access,
    issue_id: uuid.UUID,
    action: str,
    node_id: uuid.UUID | None,
    on: date,
    notes: str | None,
) -> TerritoryIssue:
    del access  # authorization is ensure_national, in the router
    issue = await _open_issue(db, issue_id)
    body = await db.get(Body, issue.body_id)
    assert body is not None  # noqa: S101 - FK
    if issue.kind == IssueKind.COMMITTEE_WITHOUT_TERRITORY:
        if action == "reassign":
            await _reassign(db, body, node_id)
            await _sync_holders(db, body)
        elif action == "dissolve":
            await _end_current(db, pk(body), on, "Disolución por cambio de marco geográfico.")
            body.dissolved_on = max(on, body.installed_on or on)
            body.dissolution_agreement = notes
        else:
            raise BadRequestError("Un comité sin territorio se reasigna o se disuelve.")
    elif action == "close":
        await _end_current(db, pk(body), on, "Cierre por cambio de marco geográfico.")
        coordination = await coordinations.load(db, pk(body))
        for row in await coordinations.current_rows(db, coordination):
            row.removed_on = on
        body.dissolved_on = max(on, body.installed_on or on)
        body.dissolution_agreement = notes
    elif action != "accept":
        raise BadRequestError("Una coordinación se acepta con su territorio actual o se cierra.")
    _close(issue, user_id, action, notes)
    await db.commit()
    return issue


async def _reassign(db: AsyncSession, body: Body, node_id: uuid.UUID | None) -> None:
    if node_id is None:
        raise BadRequestError("Indica el nuevo territorio del comité.")
    column = next(c for c in _COMMITTEE_NODES if getattr(body, c) is not None)
    if column != "municipality_id":
        # A district committee keeps its kind of district.
        column = (
            "federal_district_id"
            if body.district_kind == DistrictKind.FEDERAL
            else "local_district_id"
        )
    table, _ = _COMMITTEE_NODES[column]
    framework_id = await active_framework(db)
    state_code = (
        await db.execute(
            text(
                f"SELECT st.state_code FROM geography.{table} n "  # noqa: S608 - fixed tables
                "JOIN geography.states st ON st.id = n.state_id "
                "WHERE n.id = :node AND n.framework_id = :fw AND n.is_active"
            ),
            {"node": node_id, "fw": framework_id},
        )
    ).scalar_one_or_none()
    if state_code is None:
        raise BadRequestError(
            "Ese territorio no existe en el marco activo o no es del tipo del comité."
        )
    taken = (
        await db.execute(
            select(col(Body.id)).where(
                col(Body.body_type_id) == body.body_type_id,
                getattr(Body, column) == node_id,
                col(Body.dissolved_on).is_(None),
                col(Body.deleted_at).is_(None),
                col(Body.id) != body.id,
            )
        )
    ).first()
    if taken is not None:
        raise ConflictError("Ya hay un comité de ese tipo instalado en ese territorio.")
    for other in _COMMITTEE_NODES:
        setattr(body, other, None)
    setattr(body, column, node_id)
    body.framework_id = framework_id
    body.state_code = int(state_code)
    await db.flush()
