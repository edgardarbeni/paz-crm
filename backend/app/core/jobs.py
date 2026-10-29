"""Scheduled jobs (D-84): cron in the `scheduler` container runs `paz` commands. Each job takes
a PostgreSQL advisory lock so two runs (overlapping schedules, a manual run, two replicas)
never execute the same job at once."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

logger = get_logger(__name__)


def lock_key(job: str) -> int:
    """Stable signed 64-bit key for `pg_try_advisory_lock`, derived from the job name."""
    digest = hashlib.sha256(f"paz-job:{job}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def exclusive_job(engine: AsyncEngine, job: str) -> AsyncIterator[bool]:
    """Yields True if this process holds the job's lock; False if another run holds it.

    The lock lives on a dedicated connection for the whole run and is released at the end,
    or by PostgreSQL if the process dies."""
    async with engine.connect() as connection:
        key = lock_key(job)
        acquired = bool(
            (
                await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            ).scalar_one()
        )
        if not acquired:
            logger.warning("job_already_running", job=job)
            yield False
            return
        logger.info("job_started", job=job)
        try:
            yield True
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            await connection.commit()
            logger.info("job_finished", job=job)
