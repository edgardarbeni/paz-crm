"""Unit-of-work hook: audit every ORM write flushed through an `AuditedSession`.

Table models are audited by default. Class-level knobs:

- ``__audit__ = False``: skip the model (e.g. bulk-imported geography, D-36).
- ``__audit_masked__ = frozenset({...})``: attributes stored as ``"***"`` (secrets, hashes).
- ``__audit_ignore_fields__ = frozenset({...})``: bookkeeping attributes (e.g. ``last_seen_at``);
  an update that only touches them is not recorded.

Bytes values (ciphertexts, blind indexes) are always masked.

A session may skip whole tables with ``session.info["audit_skip_tables"] = {"schema.table"}``:
bulk paths (imports) audit them with one `record_bulk` entry per batch instead (D-90).

Writes issued as Core statements (``update(...)``, ``insert(...)``) bypass this hook; services
must use the ORM for audited writes or call `record_audit` explicitly.
"""

from typing import Any, cast

from sqlalchemy import event, inspect
from sqlalchemy.orm import InstanceState, Session, UOWTransaction
from sqlalchemy.orm.base import LoaderCallableStatus

from app.core.audit.writer import MASK, append_sync


class AuditedSession(Session):
    """Sync session class used under every `AsyncSession` of the application."""


def _state(obj: object) -> InstanceState[Any]:
    return cast(InstanceState[Any], inspect(obj))


def _is_audited(obj: object, skipped: frozenset[str] = frozenset()) -> bool:
    if not (getattr(type(obj), "__audit__", True) and hasattr(type(obj), "__table__")):
        return False
    return not skipped or _entity(obj)[0] not in skipped


def _masked(obj: object) -> frozenset[str]:
    masked: frozenset[str] = getattr(type(obj), "__audit_masked__", frozenset())
    return masked


def _ignored(obj: object) -> frozenset[str]:
    ignored: frozenset[str] = getattr(type(obj), "__audit_ignore_fields__", frozenset())
    return ignored | {"updated_at"}


def _entity(obj: object) -> tuple[str, str | None]:
    table = type(obj).__table__  # type: ignore[attr-defined]
    name = f"{table.schema}.{table.name}" if table.schema else table.name
    # New objects have no identity key yet in after_flush, but their PK values are populated.
    identity = _state(obj).mapper.primary_key_from_instance(obj)
    entity_id = ",".join(str(part) for part in identity) if any(identity) else None
    return name, entity_id


def _value(obj: object, key: str, value: Any) -> Any:
    return MASK if key in _masked(obj) else value


def _snapshot(obj: object) -> dict[str, Any]:
    state = _state(obj)
    snapshot: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        value = state.attrs[attr.key].loaded_value
        if value is not LoaderCallableStatus.NO_VALUE:
            snapshot[attr.key] = _value(obj, attr.key, value)
    return snapshot


def _changes(obj: object) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _state(obj)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        if not history.has_changes():
            continue
        before[attr.key] = _value(obj, attr.key, history.deleted[0] if history.deleted else None)
        after[attr.key] = _value(obj, attr.key, history.added[0] if history.added else None)
    return before, after


@event.listens_for(AuditedSession, "after_flush")
def _audit_after_flush(session: Session, _: UOWTransaction) -> None:
    # In after_flush the new/dirty/deleted collections and attribute history still describe
    # the flush that just happened, while primary keys are already populated.
    connection = session.connection()
    skipped: frozenset[str] = frozenset(session.info.get("audit_skip_tables", ()))

    for obj in session.new:
        if _is_audited(obj, skipped):
            table, entity_id = _entity(obj)
            append_sync(
                connection,
                action="create",
                entity_table=table,
                entity_id=entity_id,
                after=_snapshot(obj),
            )

    for obj in session.dirty:
        if not _is_audited(obj, skipped) or not session.is_modified(obj, include_collections=False):
            continue
        before, after = _changes(obj)
        if not set(after) - _ignored(obj):
            continue
        restored_or_deleted = "deleted_at" in after
        if restored_or_deleted and after["deleted_at"] is not None:
            action = "soft_delete"
        elif restored_or_deleted:
            action = "restore"
        else:
            action = "update"
        table, entity_id = _entity(obj)
        append_sync(
            connection,
            action=action,
            entity_table=table,
            entity_id=entity_id,
            before=before,
            after=after,
        )

    for obj in session.deleted:
        if _is_audited(obj, skipped):
            table, entity_id = _entity(obj)
            append_sync(
                connection,
                action="delete",
                entity_table=table,
                entity_id=entity_id,
                before=_snapshot(obj),
            )
