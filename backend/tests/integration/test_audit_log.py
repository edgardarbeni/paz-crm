"""Immutable, hash-chained audit log (D-37)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlmodel import SQLModel

from app.core.audit import (
    ensure_partitions,
    record_access,
    record_audit,
    record_bulk,
    verify_chain,
)
from app.core.context import RequestContext, set_context
from app.core.db.base import BusinessTable
from app.core.db.session import build_sessionmaker
from tests.conftest import APP_USER, Database


class AuditProbe(BusinessTable, table=True):
    """Test-only audited table (created in the `identity` schema by the fixture)."""

    __tablename__ = "audit_probes"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "identity"}
    __audit_masked__: ClassVar[frozenset[str]] = frozenset({"secret"})

    name: str
    secret: str | None = None
    payload: bytes | None = None


class UnauditedProbe(BusinessTable, table=True):
    __tablename__ = "unaudited_probes"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "identity"}
    __audit__: ClassVar[bool] = False

    name: str


PROBE_TABLES = ("audit_probes", "unaudited_probes")


@pytest.fixture(scope="module")
async def probe_tables(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    tables = [SQLModel.metadata.tables[f"identity.{name}"] for name in PROBE_TABLES]
    async with owner_engine.begin() as connection:
        for table in tables:
            await connection.run_sync(table.create)
    yield
    async with owner_engine.begin() as connection:
        for table in tables:
            await connection.run_sync(table.drop)


async def _entries(engine: AsyncEngine, entity_id: str) -> list[Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT action, before, after, actor_user_id, request_id, actor_ip::text AS ip "
                "FROM audit.audit_log WHERE entity_id = :id ORDER BY chain_seq"
            ),
            {"id": entity_id},
        )
        return list(result.mappings())


@pytest.mark.usefixtures("probe_tables")
async def test_orm_writes_are_audited_with_context_and_masking(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    actor = uuid.uuid4()
    set_context(
        RequestContext(
            request_id="req-audit-0001",
            client_ip="10.1.2.3",
            user_agent="pytest",
            actor_user_id=actor,
        )
    )
    sessionmaker = build_sessionmaker(app_engine)

    async with sessionmaker() as session, session.begin():
        probe = AuditProbe(name="Planilla", secret="s3cr3t", payload=b"\x00cipher")
        session.add(probe)
    entity_id = str(probe.id)

    async with sessionmaker() as session, session.begin():
        stored = await session.get(AuditProbe, probe.id)
        assert stored is not None
        stored.name = "Planilla 2"
        stored.secret = "otro"
    async with sessionmaker() as session, session.begin():
        stored = await session.get(AuditProbe, probe.id)
        assert stored is not None
        stored.deleted_at = datetime.now(UTC)
    async with sessionmaker() as session, session.begin():
        stored = await session.get(AuditProbe, probe.id)
        assert stored is not None
        stored.deleted_at = None
    async with sessionmaker() as session, session.begin():
        stored = await session.get(AuditProbe, probe.id)
        assert stored is not None
        await session.delete(stored)

    entries = await _entries(owner_engine, entity_id)
    assert [e["action"] for e in entries] == [
        "create",
        "update",
        "soft_delete",
        "restore",
        "delete",
    ]
    create, update, *_, delete = entries
    assert create["after"]["name"] == "Planilla"
    assert create["after"]["secret"] == "***"
    assert create["after"]["payload"] == "***"
    assert update["before"] == {"name": "Planilla", "secret": "***"}
    assert update["after"]["name"] == "Planilla 2"
    assert delete["before"]["name"] == "Planilla 2"
    assert {(e["actor_user_id"], e["request_id"], e["ip"]) for e in entries} == {
        (actor, "req-audit-0001", "10.1.2.3/32")
    }

    async with owner_engine.connect() as connection:
        assert (await verify_chain(connection)).ok


@pytest.mark.usefixtures("probe_tables")
async def test_opt_out_and_rollback_leave_no_entries(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    sessionmaker = build_sessionmaker(app_engine)
    async with sessionmaker() as session, session.begin():
        unaudited = UnauditedProbe(name="importado")
        session.add(unaudited)

    async with sessionmaker() as session:
        await session.begin()
        rolled_back = AuditProbe(name="no se confirma")
        session.add(rolled_back)
        await session.flush()
        await session.rollback()

    assert await _entries(owner_engine, str(unaudited.id)) == []
    assert await _entries(owner_engine, str(rolled_back.id)) == []


async def test_explicit_entry(app_engine: AsyncEngine) -> None:
    set_context(RequestContext(request_id="req-login-0001"))
    async with AsyncSession(app_engine) as session, session.begin():
        seq = await record_audit(session, action="login", after={"email": "a@paz.mx"})
    assert seq >= 1
    async with app_engine.connect() as connection:
        assert (await verify_chain(connection)).ok


async def test_app_role_cannot_write_directly(app_engine: AsyncEngine) -> None:
    statements = [
        "INSERT INTO audit.audit_log (occurred_at, id, chain_seq, action, prev_hash, entry_hash) "
        "VALUES (now(), uuidv7(), 999999, 'forged', '\\x00', '\\x00')",
        "UPDATE audit.audit_log SET action = 'x'",
        "DELETE FROM audit.audit_log",
        "UPDATE audit.chain_head SET last_seq = 0",
        "SELECT audit.ensure_partitions(1)",
    ]
    for statement in statements:
        async with app_engine.connect() as connection:
            with pytest.raises(DBAPIError, match="permission denied"):
                await connection.execute(text(statement))


async def test_even_the_owner_cannot_mutate(owner_engine: AsyncEngine) -> None:
    async with AsyncSession(owner_engine) as session, session.begin():
        await record_audit(session, action="probe")
    for statement in (
        "UPDATE audit.audit_log SET action = 'x'",
        "DELETE FROM audit.audit_log",
        "TRUNCATE audit.audit_log",
        "DELETE FROM audit.chain_head",
    ):
        async with owner_engine.connect() as connection:
            with pytest.raises(DBAPIError, match="append-only"):
                await connection.execute(text(statement))


async def _owner(database: Database, name: str) -> AsyncEngine:
    return create_async_engine(database.owner_url(name))


async def _append_many(engine: AsyncEngine, count: int) -> None:
    async with AsyncSession(engine) as session, session.begin():
        for index in range(count):
            await record_audit(session, action="probe", entity_id=str(index), after={"i": index})


async def test_tampering_is_detected(database: Database, fresh_database: str) -> None:
    engine = await _owner(database, fresh_database)
    try:
        await _append_many(engine, 5)
        async with engine.begin() as connection:
            assert (await verify_chain(connection)).ok
            # A superuser bypassing triggers (replica mode) edits entry 3.
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text("UPDATE audit.audit_log SET after = '{\"i\": 99}' WHERE chain_seq = 3")
            )
        async with engine.connect() as connection:
            result = await verify_chain(connection)
        assert (result.ok, result.first_broken_seq, result.checked) == (False, 3, 2)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(("deleted_seq", "expected_broken"), [(2, 2), (5, 5)])
async def test_deleted_rows_are_detected(
    database: Database, fresh_database: str, deleted_seq: int, expected_broken: int
) -> None:
    engine = await _owner(database, fresh_database)
    try:
        await _append_many(engine, 5)
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text("DELETE FROM audit.audit_log WHERE chain_seq = :seq"), {"seq": deleted_seq}
            )
        async with engine.connect() as connection:
            result = await verify_chain(connection)
            partial = await verify_chain(connection, from_seq=deleted_seq + 1)
        assert result.first_broken_seq == expected_broken
        assert partial.first_broken_seq == deleted_seq
    finally:
        await engine.dispose()


async def test_concurrent_writers_keep_a_valid_chain(
    database: Database, fresh_database: str
) -> None:
    engine = create_async_engine(database.app_url(fresh_database), pool_size=10)
    try:
        await asyncio.gather(*(_append_many(engine, 3) for _ in range(10)))
        async with engine.connect() as connection:
            result = await verify_chain(connection)
            seqs = list(
                (
                    await connection.execute(
                        text("SELECT chain_seq FROM audit.audit_log ORDER BY chain_seq")
                    )
                ).scalars()
            )
        assert result.ok
        assert seqs == list(range(1, 31))
    finally:
        await engine.dispose()


async def test_partitions(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        assert await ensure_partitions(connection, months_ahead=3) == []
        created = await ensure_partitions(connection, months_ahead=5)
        assert len(created) == 4  # two months for audit_log and two for access_log
        await connection.execute(
            text("SELECT audit.append_entry(NULL,NULL,NULL,NULL,'p',NULL,NULL,NULL,NULL)")
        )
        in_default = (
            await connection.execute(text("SELECT count(*) FROM audit.audit_log_default"))
        ).scalar_one()
    assert in_default == 0
    assert APP_USER  # grants for the app role are exercised in test_app_role_cannot_write_directly


async def test_action_is_required(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="action is required"):
            await connection.execute(
                text("SELECT audit.append_entry(NULL,NULL,NULL,NULL,'',NULL,NULL,NULL,NULL)")
            )


async def test_bulk_entry_lists_the_ids(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    ids = [uuid.uuid4() for _ in range(3)]
    async with app_engine.begin() as connection:
        await record_bulk(
            connection,
            action="probe_bulk",
            entity_table="identity.audit_probes",
            entity_ids=ids,
            details={"reason": "prueba"},
        )
    async with owner_engine.connect() as connection:
        after = (
            await connection.execute(
                text("SELECT after FROM audit.audit_log WHERE action = 'probe_bulk'")
            )
        ).scalar_one()
    assert after == {"count": 3, "ids": [str(i) for i in ids], "reason": "prueba"}


async def test_access_log_is_append_only_and_outside_the_chain(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    actor = uuid.uuid4()
    set_context(
        RequestContext(request_id="req-access-1", client_ip="10.9.9.9", actor_user_id=actor)
    )
    async with owner_engine.connect() as connection:
        head_before = (
            await connection.execute(text("SELECT last_seq FROM audit.chain_head"))
        ).scalar_one()
    async with app_engine.begin() as connection:
        await record_access(
            connection,
            action="read",
            entity_table="people.persons",
            entity_id="p-1",
            details={"unmasked": True},
        )
    async with owner_engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT actor_user_id, actor_ip::text AS ip, request_id, details "
                        "FROM audit.access_log WHERE entity_id = 'p-1'"
                    )
                )
            )
            .mappings()
            .one()
        )
        head_after = (
            await connection.execute(text("SELECT last_seq FROM audit.chain_head"))
        ).scalar_one()
    assert row == {
        "actor_user_id": actor,
        "ip": "10.9.9.9/32",
        "request_id": "req-access-1",
        "details": {"unmasked": True},
    }
    assert head_after == head_before  # reads never touch the chain

    async with app_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="permission denied"):
            await connection.execute(
                text("INSERT INTO audit.access_log (action, entity_table) VALUES ('read', 'x')")
            )
    async with owner_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="append-only"):
            await connection.execute(text("DELETE FROM audit.access_log"))
    async with owner_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="append-only"):
            await connection.execute(text("TRUNCATE audit.access_log"))
    async with owner_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="required"):
            await connection.execute(
                text("SELECT audit.record_access(NULL,NULL,NULL,NULL,'',NULL,NULL,NULL)")
            )
