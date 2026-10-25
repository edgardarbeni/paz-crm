"""Read-only mapping of `audit.audit_log` (its DDL lives in migration 0002, outside the ORM
metadata so autogenerate never touches it)."""

from sqlalchemy import BigInteger, Column, DateTime, LargeBinary, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

audit_metadata = MetaData(schema="audit")

audit_log = Table(
    "audit_log",
    audit_metadata,
    Column("occurred_at", DateTime(timezone=True), primary_key=True),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("chain_seq", BigInteger, nullable=False),
    Column("actor_user_id", UUID(as_uuid=True)),
    Column("actor_ip", INET),
    Column("user_agent", Text),
    Column("request_id", Text),
    Column("action", Text, nullable=False),
    Column("entity_table", Text),
    Column("entity_id", Text),
    Column("before", JSONB),
    Column("after", JSONB),
    Column("prev_hash", LargeBinary, nullable=False),
    Column("entry_hash", LargeBinary, nullable=False),
)
