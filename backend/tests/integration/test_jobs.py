"""Scheduled jobs take an advisory lock so two runs never overlap (D-84)."""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.jobs import exclusive_job, lock_key


def test_lock_keys_are_stable_and_distinct() -> None:
    assert lock_key("people.purge") == lock_key("people.purge")
    assert lock_key("people.purge") != lock_key("audit.ensure_partitions")
    assert -(2**63) <= lock_key("people.purge") < 2**63


async def test_a_second_run_does_not_start(app_engine: AsyncEngine) -> None:
    async with exclusive_job(app_engine, "probe.job") as first:
        assert first is True
        async with exclusive_job(app_engine, "probe.job") as second:
            assert second is False
        async with exclusive_job(app_engine, "probe.other") as other:
            assert other is True
    # Released at the end of the run.
    async with exclusive_job(app_engine, "probe.job") as again:
        assert again is True
