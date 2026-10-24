"""Audit-log maintenance: chain verification and monthly partitions."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class ChainVerification:
    checked: int
    first_broken_seq: int | None

    @property
    def ok(self) -> bool:
        return self.first_broken_seq is None


async def verify_chain(connection: AsyncConnection, *, from_seq: int = 1) -> ChainVerification:
    row = (
        await connection.execute(
            text("SELECT checked, first_broken_seq FROM audit.verify_chain(:from_seq)"),
            {"from_seq": from_seq},
        )
    ).one()
    return ChainVerification(checked=int(row.checked), first_broken_seq=row.first_broken_seq)


async def ensure_partitions(connection: AsyncConnection, *, months_ahead: int = 3) -> list[str]:
    """Creates missing monthly partitions (requires the owner role). Returns created names."""
    result = await connection.execute(
        text("SELECT audit.ensure_partitions(:months_ahead)"), {"months_ahead": months_ahead}
    )
    created: list[str] = result.scalar_one() or []
    return created
