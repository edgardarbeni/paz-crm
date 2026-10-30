"""Network aggregates (docs/modules/peace-movement.md, «Cómo se evita la recursión infinita»).

- **Incremental** (every minute, `paz peace-movement aggregate`): takes pending
  `network_changes`, collects the ancestor chains they touch and recomputes those nodes bottom
  up. A node's counters are the sum of its direct recruits' counters, so each recompute reads
  only direct children (index on `recruited_by_member_id`): no network is counted on the fly
  and the top of the pyramid sees one batched update, not one per enrollment.
- **Full** (nightly, `--full`): recomputes every node from scratch by exploding each active
  member's path into its ancestors, which corrects any drift, rebuilds the daily enrollment
  counts and re-checks house consolidation against the goals in force.

Both run under the job's advisory lock (D-84). Derived tables are not audited row by row; each
run leaves one entry in the audit log (D-90).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.audit import record_audit
from app.modules.peace_movement.models import CURRENT_HOUSE_STATUSES, PeaceHouse

BATCH = 5000
COUNTED_STATUSES = ("active", "left", "withdrawn")  # validated enrollments, for growth

_UPSERT = """
    ON CONFLICT (member_id) DO UPDATE SET
      direct_active = EXCLUDED.direct_active,
      direct_pending = EXCLUDED.direct_pending,
      network_total = EXCLUDED.network_total,
      network_by_level = EXCLUDED.network_by_level,
      houses_open = EXCLUDED.houses_open,
      houses_consolidated = EXCLUDED.houses_consolidated,
      computed_at = EXCLUDED.computed_at
"""

# Recomputes the given nodes from their direct recruits' stats (deepest level first).
_NODES_SQL = (
    """
    WITH targets AS (
      SELECT id FROM peace_movement.members WHERE tree_id = ANY(:ids) AND deleted_at IS NULL
    ),
    kids AS (
      SELECT c.recruited_by_member_id AS parent, c.status, l.code,
             cs.network_total, cs.network_by_level
      FROM peace_movement.members c
      JOIN peace_movement.participation_levels l ON l.id = c.level_id
      LEFT JOIN peace_movement.member_network_stats cs ON cs.member_id = c.id
      WHERE c.recruited_by_member_id IN (SELECT id FROM targets) AND c.deleted_at IS NULL
    ),
    counts AS (
      SELECT parent,
             count(*) FILTER (WHERE status = 'active') AS direct_active,
             count(*) FILTER (WHERE status = 'pending_validation') AS direct_pending,
             sum(coalesce(network_total, 0) + (status = 'active')::int) AS network_total
      FROM kids GROUP BY parent
    ),
    levels AS (
      SELECT parent, jsonb_object_agg(code, n) AS by_level FROM (
        SELECT parent, code, sum(n)::int AS n FROM (
          SELECT parent, code, 1 AS n FROM kids WHERE status = 'active'
          UNION ALL
          SELECT k.parent, e.key, e.value::int
          FROM kids k, jsonb_each_text(coalesce(k.network_by_level, '{}'::jsonb)) e
        ) x GROUP BY parent, code
      ) y GROUP BY parent
    ),
    houses AS (
      SELECT credited_member_id AS member_id,
             count(*) FILTER (WHERE status = 'open') AS open,
             count(*) FILTER (WHERE status = 'consolidated') AS consolidated
      FROM peace_movement.peace_houses
      WHERE credited_member_id IN (SELECT id FROM targets) AND deleted_at IS NULL
      GROUP BY credited_member_id
    )
    INSERT INTO peace_movement.member_network_stats (member_id, direct_active, direct_pending,
      network_total, network_by_level, houses_open, houses_consolidated, computed_at)
    SELECT t.id, coalesce(c.direct_active, 0), coalesce(c.direct_pending, 0),
           coalesce(c.network_total, 0), coalesce(l.by_level, '{}'::jsonb),
           coalesce(h.open, 0), coalesce(h.consolidated, 0), now()
    FROM targets t
    LEFT JOIN counts c ON c.parent = t.id
    LEFT JOIN levels l ON l.parent = t.id
    LEFT JOIN houses h ON h.member_id = t.id
    """
    + _UPSERT
)

# Every node at once: each active member counts once for each of its ancestors (path labels).
_FULL_SQL = (
    """
    WITH active AS (
      SELECT string_to_array(m.path::text, '.')::bigint[] AS labels, l.code
      FROM peace_movement.members m
      JOIN peace_movement.participation_levels l ON l.id = m.level_id
      WHERE m.status = 'active' AND m.deleted_at IS NULL AND m.depth > 0
    ),
    per_level AS (
      SELECT a.labels[i] AS ancestor, a.code, count(*)::int AS n
      FROM active a, generate_series(1, array_length(a.labels, 1) - 1) AS i
      GROUP BY 1, 2
    ),
    per_node AS (
      SELECT ancestor, sum(n)::int AS total, jsonb_object_agg(code, n) AS by_level
      FROM per_level GROUP BY ancestor
    ),
    direct AS (
      SELECT recruited_by_member_id AS parent,
             count(*) FILTER (WHERE status = 'active') AS active,
             count(*) FILTER (WHERE status = 'pending_validation') AS pending
      FROM peace_movement.members
      WHERE recruited_by_member_id IS NOT NULL AND deleted_at IS NULL
      GROUP BY recruited_by_member_id
    ),
    houses AS (
      SELECT credited_member_id AS member_id,
             count(*) FILTER (WHERE status = 'open') AS open,
             count(*) FILTER (WHERE status = 'consolidated') AS consolidated
      FROM peace_movement.peace_houses
      WHERE credited_member_id IS NOT NULL AND deleted_at IS NULL
      GROUP BY credited_member_id
    )
    INSERT INTO peace_movement.member_network_stats (member_id, direct_active, direct_pending,
      network_total, network_by_level, houses_open, houses_consolidated, computed_at)
    SELECT m.id, coalesce(d.active, 0), coalesce(d.pending, 0), coalesce(p.total, 0),
           coalesce(p.by_level, '{}'::jsonb), coalesce(h.open, 0), coalesce(h.consolidated, 0),
           now()
    FROM peace_movement.members m
    LEFT JOIN per_node p ON p.ancestor = m.tree_id
    LEFT JOIN direct d ON d.parent = m.id
    LEFT JOIN houses h ON h.member_id = m.id
    WHERE m.deleted_at IS NULL
    """
    + _UPSERT
)

_DAILY_SQL = """
    INSERT INTO peace_movement.enrollment_daily_counts (day, level_id, section_id, enrollments)
    SELECT enrolled_on, level_id, section_id, count(*)
    FROM peace_movement.members
    WHERE status = ANY(:statuses) AND deleted_at IS NULL {where}
    GROUP BY enrolled_on, level_id, section_id
"""


_SECTIONS_SQL = """
    INSERT INTO peace_movement.member_section_counts (section_id, level_id, active)
    SELECT section_id, level_id, count(*)
    FROM peace_movement.members
    WHERE status = 'active' AND deleted_at IS NULL {where}
    GROUP BY section_id, level_id
"""


@dataclass(frozen=True, slots=True)
class AggregationReport:
    changes: int
    nodes: int
    days: int
    houses_checked: int = 0


async def apply_changes(db: AsyncSession, *, batch: int = BATCH) -> AggregationReport:
    """Incremental run over one batch of pending changes (caller holds the job lock)."""
    await db.execute(text("SET LOCAL statement_timeout = '5min'"))
    pending = (
        await db.execute(
            text(
                "SELECT id, member_id, paths, payload FROM peace_movement.network_changes "
                "WHERE processed_at IS NULL ORDER BY id LIMIT :batch FOR UPDATE SKIP LOCKED"
            ),
            {"batch": batch},
        )
    ).all()
    if not pending:
        return AggregationReport(changes=0, nodes=0, days=0)
    tree_ids: set[int] = set()
    for _, _, paths, _ in pending:
        for path in paths or []:
            tree_ids.update(int(label) for label in path.split("."))
    member_ids = [row.member_id for row in pending if row.member_id is not None]
    old_sections = {
        str(row.payload["old_section_id"])
        for row in pending
        if row.payload and row.payload.get("old_section_id")
    }
    nodes = await _recompute(db, tree_ids)
    days = await _rebuild_days(db, member_ids)
    await _rebuild_sections(db, member_ids, old_sections)
    await db.execute(
        text("UPDATE peace_movement.network_changes SET processed_at = now() WHERE id = ANY(:ids)"),
        {"ids": [row.id for row in pending]},
    )
    await record_audit(
        db,
        action="network_aggregated",
        entity_table="peace_movement.member_network_stats",
        after={"changes": len(pending), "nodes": nodes, "days": days},
    )
    await db.commit()
    return AggregationReport(changes=len(pending), nodes=nodes, days=days)


async def _recompute(db: AsyncSession, tree_ids: set[int]) -> int:
    if not tree_ids:
        return 0
    depths = (
        await db.execute(
            text(
                "SELECT depth, array_agg(tree_id) FROM peace_movement.members "
                "WHERE tree_id = ANY(:ids) GROUP BY depth ORDER BY depth DESC"
            ),
            {"ids": list(tree_ids)},
        )
    ).all()
    total = 0
    for _, ids in depths:  # children before parents
        await db.execute(text(_NODES_SQL), {"ids": list(ids)})
        total += len(ids)
    return total


async def _rebuild_days(db: AsyncSession, member_ids: list[uuid.UUID]) -> int:
    if not member_ids:
        return 0
    days = list(
        (
            await db.execute(
                text(
                    "SELECT DISTINCT enrolled_on FROM peace_movement.members WHERE id = ANY(:ids)"
                ),
                {"ids": member_ids},
            )
        ).scalars()
    )
    if not days:
        return 0
    await db.execute(
        text("DELETE FROM peace_movement.enrollment_daily_counts WHERE day = ANY(:days)"),
        {"days": days},
    )
    await db.execute(
        text(_DAILY_SQL.format(where="AND enrolled_on = ANY(:days)")),
        {"statuses": list(COUNTED_STATUSES), "days": days},
    )
    return len(days)


async def _rebuild_sections(db: AsyncSession, member_ids: list[uuid.UUID], extra: set[str]) -> None:
    if not member_ids and not extra:
        return
    sections = list(
        (
            await db.execute(
                text("SELECT DISTINCT section_id FROM peace_movement.members WHERE id = ANY(:ids)"),
                {"ids": member_ids},
            )
        ).scalars()
    )
    sections = list({*sections, *(uuid.UUID(s) for s in extra)})
    await db.execute(
        text("DELETE FROM peace_movement.member_section_counts WHERE section_id = ANY(:s)"),
        {"s": sections},
    )
    await db.execute(text(_SECTIONS_SQL.format(where="AND section_id = ANY(:s)")), {"s": sections})


async def rebuild_all(db: AsyncSession) -> AggregationReport:
    """Nightly full recompute (caller holds the job lock)."""
    from app.modules.peace_movement.houses import sync_status  # noqa: PLC0415 - avoids a cycle

    high_water = (
        await db.execute(text("SELECT coalesce(max(id), 0) FROM peace_movement.network_changes"))
    ).scalar_one()
    # A job, not a request: the API's statement timeout (PAZ_DATABASE_STATEMENT_TIMEOUT_MS)
    # would cancel the recompute of a large network.
    await db.execute(text("SET LOCAL statement_timeout = '30min'"))
    await db.execute(text("SET LOCAL work_mem = '256MB'"))
    nodes = (await db.execute(text(_FULL_SQL))).rowcount  # type: ignore[attr-defined]
    await db.execute(text("DELETE FROM peace_movement.member_section_counts"))
    await db.execute(text(_SECTIONS_SQL.format(where="")))
    await db.execute(text("DELETE FROM peace_movement.enrollment_daily_counts"))
    await db.execute(text(_DAILY_SQL.format(where="")), {"statuses": list(COUNTED_STATUSES)})
    days = (
        await db.execute(
            text("SELECT count(DISTINCT day) FROM peace_movement.enrollment_daily_counts")
        )
    ).scalar_one()
    houses = list(
        (
            await db.execute(
                select(PeaceHouse).where(
                    col(PeaceHouse.status).in_(CURRENT_HOUSE_STATUSES),
                    col(PeaceHouse.deleted_at).is_(None),
                )
            )
        ).scalars()
    )
    for house in houses:  # goals may have changed since the last membership change
        await sync_status(db, house)
    await db.execute(
        text(
            "UPDATE peace_movement.network_changes SET processed_at = now() "
            "WHERE processed_at IS NULL AND id <= :high"
        ),
        {"high": high_water},
    )
    await record_audit(
        db,
        action="network_rebuilt",
        entity_table="peace_movement.member_network_stats",
        after={"nodes": nodes, "days": int(days), "houses_checked": len(houses)},
    )
    await db.commit()
    return AggregationReport(changes=0, nodes=nodes, days=int(days), houses_checked=len(houses))


async def drain(
    db: AsyncSession, *, batch: int = BATCH, max_batches: int = 100
) -> AggregationReport:
    """Applies batches until the outbox is empty (bounded)."""
    changes = nodes = days = 0
    for _ in range(max_batches):
        report = await apply_changes(db, batch=batch)
        if report.changes == 0:
            break
        changes += report.changes
        nodes += report.nodes
        days += report.days
    return AggregationReport(changes=changes, nodes=nodes, days=days)
