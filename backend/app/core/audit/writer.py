"""Append entries to the immutable audit log (D-37).

The hash chain lives in PostgreSQL: `audit.append_entry(...)` (SECURITY DEFINER) locks the
chain head, computes the entry hash and inserts the row. The application role can only
execute that function and read the table; it cannot INSERT/UPDATE/DELETE directly.

Two ways to write:
- Automatically: every ORM flush through an `AuditedSession` records create / update /
  soft_delete / delete entries (see `hooks.py`).
- Explicitly: `record_audit(...)` for events that are not row changes (login, import…).
"""

import datetime as dt
import decimal
import enum
import uuid
from typing import Any

import orjson
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.context import RequestContext, get_context

_APPEND_SQL = text(
    "SELECT audit.append_entry("
    "CAST(:actor AS uuid), CAST(:ip AS inet), :user_agent, :request_id, :action, "
    ":entity_table, :entity_id, CAST(:before AS jsonb), CAST(:after AS jsonb))"
)

MASK = "***"


def _default(value: Any) -> Any:
    if isinstance(value, uuid.UUID | dt.date | dt.datetime | dt.time | decimal.Decimal):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, bytes | bytearray | memoryview):
        return MASK
    if isinstance(value, set | frozenset):
        return sorted(value, key=str)
    return f"<{type(value).__name__}>"


def to_json(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return orjson.dumps(payload, default=_default, option=orjson.OPT_SORT_KEYS).decode()


def _params(
    context: RequestContext,
    *,
    action: str,
    entity_table: str | None,
    entity_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "actor": str(context.actor_user_id) if context.actor_user_id else None,
        "ip": context.client_ip,
        "user_agent": context.user_agent,
        "request_id": context.request_id,
        "action": action,
        "entity_table": entity_table,
        "entity_id": entity_id,
        "before": to_json(before),
        "after": to_json(after),
    }


def append_sync(
    connection: Connection,
    *,
    action: str,
    entity_table: str | None = None,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> int:
    params = _params(
        get_context(),
        action=action,
        entity_table=entity_table,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    return int(connection.execute(_APPEND_SQL, params).scalar_one())


async def record_audit(
    target: AsyncSession | AsyncConnection,
    *,
    action: str,
    entity_table: str | None = None,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> int:
    """Explicit audit entry inside the caller's transaction. Returns its chain sequence."""
    params = _params(
        get_context(),
        action=action,
        entity_table=entity_table,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    result = await target.execute(_APPEND_SQL, params)
    return int(result.scalar_one())
