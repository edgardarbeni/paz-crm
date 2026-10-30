"""Statistics and reports of the Peace Movement (phase 3).

- A member's network comes from `member_network_stats` (precomputed) plus descendants within a
  bounded depth (`max_depth` ≤ 3), never the whole network.
- Geographic statistics filter by the geographic scope; network statistics by the member scope
  (geographic or branch, D-83).
- Exports are capped and logged in `audit.access_log` (D-89).
"""

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.core.audit import record_access
from app.core.errors import ConflictError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.identity.services.scopes import GeoScope
from app.modules.peace_movement.members import visible_member
from app.modules.peace_movement.models import (
    Member,
    MemberNetworkStats,
    ParticipationLevel,
)
from app.modules.peace_movement.scope import member_visibility
from app.modules.people import curp as curp_rules
from app.modules.people.models import Person
from app.modules.people.service import CURP_CONTEXT, Crypto, full_name

MAX_NETWORK_DEPTH = 3
EXPORT_LIMIT = 50_000

# Level → (column of geography.sections, table, label expression)
GEO_LEVELS: dict[str, tuple[str, str, str]] = {
    "state": ("state_id", "states", "n.name"),
    "municipality": ("municipality_id", "municipalities", "n.name"),
    "federal_district": (
        "federal_district_id",
        "federal_districts",
        "'Distrito ' || n.district_number",
    ),
    "local_district": ("local_district_id", "local_districts", "'Distrito ' || n.district_number"),
    "section": ("id", "sections", "'Sección ' || lpad(n.section_number::text, 4, '0')"),
}


async def network_stats(db: AsyncSession, member: Member) -> MemberNetworkStats | None:
    return await db.get(MemberNetworkStats, member.id)


def _visible(geo: GeoScope, member: Any) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [col(member.deleted_at).is_(None)]
    scoped = member_visibility(geo, member)
    if scoped is not None:
        filters.append(scoped)
    return filters


async def descendants(
    db: AsyncSession, geo: GeoScope, member_id: uuid.UUID, params: PageParams, *, max_depth: int
) -> tuple[Member, CursorPage[Member], int]:
    """Visible descendants down to `max_depth` levels, plus how many in that range are hidden."""
    node = await visible_member(db, geo, member_id)
    depth = min(max(max_depth, 1), MAX_NETWORK_DEPTH)
    below = aliased(Member)
    in_range = [
        col(below.path).op("<@")(text("CAST(:root AS ltree)").bindparams(root=node.path)),
        col(below.depth).between(node.depth + 1, node.depth + depth),
        col(below.deleted_at).is_(None),
    ]
    statement = select(below).where(*in_range, *_visible(geo, below))
    sort = parse_sort(
        params.sort,
        allowed={"depth": col(below.depth), "enrolled_on": col(below.enrolled_on)},
        tiebreaker=col(below.id),
        default="depth,enrolled_on",
    )
    page: CursorPage[Member] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    visible = member_visibility(geo, below)
    hidden = 0
    if visible is not None:
        row = (
            await db.execute(
                select(func.count(), func.count().filter(visible))
                .select_from(below)
                .where(*in_range)
            )
        ).one()
        hidden = int(row[0]) - int(row[1])
    return node, page, hidden


async def stats_of(db: AsyncSession, members: list[Member]) -> dict[uuid.UUID, MemberNetworkStats]:
    ids = [m.id for m in members if m.id is not None]
    if not ids:
        return {}
    rows = await db.execute(
        select(MemberNetworkStats).where(col(MemberNetworkStats.member_id).in_(ids))
    )
    return {row.member_id: row for row in rows.scalars()}


@dataclass(frozen=True, slots=True)
class GeoRow:
    node_id: uuid.UUID
    label: str
    active: int
    by_level: dict[str, int]


async def by_geography(
    db: AsyncSession,
    geo: GeoScope,
    *,
    level: str,
    state_id: uuid.UUID | None = None,
    municipality_id: uuid.UUID | None = None,
) -> list[GeoRow]:
    """Active members per node of `level`, limited to the user's geographic scope. Reads the
    per-section counts the aggregates job keeps (fresh within minutes)."""
    column, table, label = GEO_LEVELS[level]
    where = ["true"]
    params: dict[str, Any] = {}
    if not geo.unrestricted:
        where.append(
            "EXISTS (SELECT 1 FROM identity.user_scope_sections u "
            "WHERE u.user_id = :user AND u.section_id = c.section_id)"
        )
        params["user"] = geo.user_id
    if state_id:
        where.append("s.state_id = :state")
        params["state"] = state_id
    if municipality_id:
        where.append("s.municipality_id = :municipality")
        params["municipality"] = municipality_id
    rows = await db.execute(
        text(
            f"""
            SELECT g.node_id, {label} AS label, sum(g.n)::int AS active,
                   jsonb_object_agg(g.code, g.n) AS by_level
            FROM (
              SELECT s.{column} AS node_id, l.code, sum(c.active)::int AS n
              FROM peace_movement.member_section_counts c
              JOIN geography.sections s ON s.id = c.section_id
              JOIN peace_movement.participation_levels l ON l.id = c.level_id
              WHERE {" AND ".join(where)}
              GROUP BY 1, 2
            ) g
            JOIN geography.{table} n ON n.id = g.node_id
            WHERE g.n > 0
            GROUP BY g.node_id, {label}
            ORDER BY active DESC, label
            """
        ),
        params,
    )
    return [GeoRow(r.node_id, r.label, r.active, dict(r.by_level)) for r in rows]


async def growth(
    db: AsyncSession,
    geo: GeoScope,
    *,
    date_from: date,
    date_to: date,
    state_id: uuid.UUID | None = None,
    level_id: uuid.UUID | None = None,
) -> list[tuple[date, int]]:
    """Validated enrollments per day in the user's geographic scope (`enrollment_daily_counts`)."""
    where = ["d.day BETWEEN :from AND :to"]
    params: dict[str, Any] = {"from": date_from, "to": date_to}
    if not geo.unrestricted:
        where.append(
            "EXISTS (SELECT 1 FROM identity.user_scope_sections u "
            "WHERE u.user_id = :user AND u.section_id = d.section_id)"
        )
        params["user"] = geo.user_id
    if state_id:
        where.append("s.state_id = :state")
        params["state"] = state_id
    if level_id:
        where.append("d.level_id = :level")
        params["level"] = level_id
    rows = await db.execute(
        text(
            f"""
            SELECT d.day, sum(d.enrollments)::int AS enrollments
            FROM peace_movement.enrollment_daily_counts d
            JOIN geography.sections s ON s.id = d.section_id
            WHERE {" AND ".join(where)}
            GROUP BY d.day ORDER BY d.day
            """
        ),
        params,
    )
    return [(r.day, r.enrollments) for r in rows]


async def export_members(
    db: AsyncSession,
    crypto: Crypto,
    geo: GeoScope,
    *,
    sensitive: bool,
    status: str | None = None,
    state_id: uuid.UUID | None = None,
    level_id: uuid.UUID | None = None,
) -> str:
    """CSV of the visible members (capped at EXPORT_LIMIT), logged as a sensitive read."""
    statement = (
        select(
            Member,
            Person,
            col(ParticipationLevel.code),
            col(MemberNetworkStats.network_total),
        )
        .join(Person, col(Person.id) == col(Member.person_id))
        .join(ParticipationLevel, col(ParticipationLevel.id) == col(Member.level_id))
        .outerjoin(MemberNetworkStats, col(MemberNetworkStats.member_id) == col(Member.id))
        .where(*_visible(geo, Member))
    )
    filters: dict[str, Any] = {}
    if status:
        statement = statement.where(col(Member.status) == status)
        filters["status"] = status
    if state_id:
        statement = statement.where(col(Member.state_id) == state_id)
        filters["state_id"] = str(state_id)
    if level_id:
        statement = statement.where(col(Member.level_id) == level_id)
        filters["level_id"] = str(level_id)
    rows = (await db.execute(statement.order_by(col(Member.path)).limit(EXPORT_LIMIT + 1))).all()
    if len(rows) > EXPORT_LIMIT:
        raise ConflictError(
            f"La exportación pasa de {EXPORT_LIMIT:,} pacificadores; acota los filtros."
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "nombre",
            "curp",
            "nivel",
            "estatus",
            "reclutador",
            "inscripcion",
            "profundidad",
            "estado_id",
            "seccion_id",
            "red_activa",
        ]
    )
    for member, person, code, network_total in rows:
        curp = None
        if person.curp_ciphertext is not None:
            value = crypto.cipher.decrypt(person.curp_ciphertext, context=CURP_CONTEXT)
            curp = value if sensitive else curp_rules.mask(value)
        writer.writerow(
            [
                member.id,
                full_name(person),
                curp or "",
                code,
                member.status,
                member.recruited_by_member_id or "",
                member.enrolled_on.isoformat(),
                member.depth,
                member.state_id,
                member.section_id,
                network_total or 0,
            ]
        )
    await record_access(
        db,
        action="export",
        entity_table="peace_movement.members",
        details={"rows": len(rows), "unmasked": sensitive, **filters},
    )
    await db.commit()
    return buffer.getvalue()
