"""Audit-log viewer (read-only, permission `audit.log.read`), limited by the reader's scope
(D-93)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.audit.table import access_log, audit_log
from app.core.db.session import SessionDep
from app.core.pagination import CursorPage, PageParams, SortField, page_params, paginate
from app.modules.audit.service import readable_entries
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm
from app.modules.identity.schemas import AccessEntryOut, AuditEntryOut

router = APIRouter(prefix="/audit-log", tags=["audit"])

_COLUMNS = [column for column in audit_log.c if column.name not in {"prev_hash", "entry_hash"}]


@router.get("", operation_id="listAuditEntries", summary="Consultar la bitácora de auditoría")
async def list_entries(
    *,
    db: SessionDep,
    user: Annotated[CurrentUser, permission(Perm.AUDIT_READ)],
    params: Annotated[PageParams, Depends(page_params)],
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=50)] = None,
    entity_table: Annotated[str | None, Query(max_length=100)] = None,
    entity_id: Annotated[str | None, Query(max_length=100)] = None,
    request_id: Annotated[str | None, Query(max_length=64)] = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> CursorPage[AuditEntryOut]:
    statement = select(*_COLUMNS)
    filters: list[Any] = []
    scoped = readable_entries(user.geo, audit_log)
    if scoped is not None:
        filters.append(scoped)
    if actor_user_id:
        filters.append(audit_log.c.actor_user_id == actor_user_id)
    if action:
        filters.append(audit_log.c.action == action)
    if entity_table:
        filters.append(audit_log.c.entity_table == entity_table)
    if entity_id:
        filters.append(audit_log.c.entity_id == entity_id)
    if request_id:
        filters.append(audit_log.c.request_id == request_id)
    if occurred_from:
        filters.append(audit_log.c.occurred_at >= occurred_from)
    if occurred_to:
        filters.append(audit_log.c.occurred_at < occurred_to)
    statement = statement.where(*filters)
    # Newest first; chain_seq is unique and follows time (D-45).
    sort = [SortField("chain_seq", audit_log.c.chain_seq, descending=True)]
    page = await paginate(db, statement, sort=sort, limit=params.limit, cursor=params.cursor)
    items = [AuditEntryOut.model_validate(row) for row in page.items]
    return CursorPage[AuditEntryOut](
        items=items, next_cursor=page.next_cursor, has_more=page.has_more
    )


@router.get(
    "/access",
    operation_id="listAccessEntries",
    summary="Consultar la bitácora de lecturas sensibles",
)
async def list_access_entries(
    *,
    db: SessionDep,
    user: Annotated[CurrentUser, permission(Perm.AUDIT_READ)],
    params: Annotated[PageParams, Depends(page_params)],
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=50)] = None,
    entity_table: Annotated[str | None, Query(max_length=100)] = None,
    entity_id: Annotated[str | None, Query(max_length=100)] = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> CursorPage[AccessEntryOut]:
    filters: list[Any] = []
    scoped = readable_entries(user.geo, access_log)
    if scoped is not None:
        filters.append(scoped)
    if actor_user_id:
        filters.append(access_log.c.actor_user_id == actor_user_id)
    if action:
        filters.append(access_log.c.action == action)
    if entity_table:
        filters.append(access_log.c.entity_table == entity_table)
    if entity_id:
        filters.append(access_log.c.entity_id == entity_id)
    if occurred_from:
        filters.append(access_log.c.occurred_at >= occurred_from)
    if occurred_to:
        filters.append(access_log.c.occurred_at < occurred_to)
    statement = select(access_log).where(*filters)
    # Newest first, following the partition key and the primary key.
    sort = [
        SortField("occurred_at", access_log.c.occurred_at, descending=True),
        SortField("id", access_log.c.id, descending=True),
    ]
    page = await paginate(db, statement, sort=sort, limit=params.limit, cursor=params.cursor)
    items = [AccessEntryOut.model_validate(row) for row in page.items]
    return CursorPage[AccessEntryOut](
        items=items, next_cursor=page.next_cursor, has_more=page.has_more
    )
