"""Network aggregates and statistics (phase 3): incremental bottom-up counters from the outbox,
the nightly full recompute, house counters, the bounded network API, geographic and growth
statistics, the CSV export and the module's commands."""

import asyncio
from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.testing import CliRunner

from app.cli import cli, mount_module_clis
from app.core.config import Settings, get_settings
from app.core.db.session import build_sessionmaker
from app.modules.peace_movement import aggregates
from tests.integration.candidacies.conftest import Geo
from tests.integration.geography.conftest import rows, scalar
from tests.integration.peace_movement.conftest import API, enroll
from tests.integration.peace_movement.test_houses import open_house


async def drain(engine: AsyncEngine) -> aggregates.AggregationReport:
    async with build_sessionmaker(engine)() as db:
        return await aggregates.drain(db)


async def counters(engine: AsyncEngine) -> dict[str, dict[str, Any]]:
    found = await rows(
        engine,
        "SELECT member_id::text AS id, direct_active, direct_pending, network_total, "
        "network_by_level, houses_open, houses_consolidated "
        "FROM peace_movement.member_network_stats",
    )
    return {row.pop("id"): row for row in found}


async def test_incremental_counters_follow_the_network(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    a = await enroll(client, root, levels, geo.sections[101])
    b = await enroll(
        client, root, levels, geo.sections[101], recruiter=a["id"], level="peace_promoter"
    )
    c = await enroll(client, root, levels, geo.sections[102], recruiter=b["id"])
    d = await enroll(client, root, levels, geo.sections[103], recruiter=a["id"])
    await client.post(f"{API}/members/{d['id']}/leave", headers=root, json={"reason": "Renuncia"})

    report = await drain(owner_engine)
    assert report.changes == 5
    stats = await counters(owner_engine)
    assert stats[a["id"]] == {
        "direct_active": 1,
        "direct_pending": 0,
        "network_total": 2,
        "network_by_level": {"peace_promoter": 1, "pacifier": 1},
        "houses_open": 0,
        "houses_consolidated": 0,
    }
    assert (stats[b["id"]]["network_total"], stats[c["id"]]["network_total"]) == (1, 0)
    assert (await drain(owner_engine)).changes == 0  # nothing pending

    detail = (await client.get(f"{API}/members/{a['id']}", headers=root)).json()
    assert detail["network"]["network_total"] == 2

    # Reassigning b (with c) under a new root moves both counters.
    e = await enroll(client, root, levels, geo.sections[104])
    moved = await client.post(
        f"{API}/members/{b['id']}/reassign",
        headers=root,
        json={"recruiter_member_id": e["id"], "reason": "Ajuste"},
    )
    assert moved.status_code == 200
    await drain(owner_engine)
    stats = await counters(owner_engine)
    assert (stats[a["id"]]["network_total"], stats[e["id"]]["network_total"]) == (0, 2)

    # The nightly recompute reaches the same numbers.
    before = await counters(owner_engine)
    async with build_sessionmaker(owner_engine)() as db:
        full = await aggregates.rebuild_all(db)
    assert full.nodes == 5
    assert await counters(owner_engine) == before
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM audit.audit_log WHERE action IN ('network_aggregated', "
            "'network_rebuilt')",
        )
        >= 3
    )


async def test_house_counters_and_ambassador_progress(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    await client.post(
        f"{API}/house-goals", headers=root, json={"state_id": geo.state, "member_goal": 2}
    )
    ambassador = await enroll(client, root, levels, geo.sections[101], level="peace_ambassador")
    helper = await enroll(client, root, levels, geo.sections[101], recruiter=ambassador["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=helper["id"], host=helper["id"], contact=ambassador["id"],
    )  # fmt: skip
    assert house["status"] == "consolidated"
    await drain(owner_engine)
    detail = (await client.get(f"{API}/members/{ambassador['id']}", headers=root)).json()
    assert detail["network"]["houses_consolidated"] == 1
    # Embajador de Paz: 5 consolidated houses nationally.
    assert (detail["house_goal"], detail["houses_progress_pct"]) == (5, 20)

    await client.post(f"{API}/houses/{house['id']}/close", headers=root, json={"reason": "Cierre"})
    await drain(owner_engine)
    assert (await counters(owner_engine))[ambassador["id"]]["houses_consolidated"] == 0


async def test_network_api_is_bounded_and_scoped(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101])
    child = await enroll(client, root, levels, geo.sections[101], recruiter=top["id"])
    far = await enroll(client, root, levels, geo.sections[103], recruiter=top["id"])
    grandchild = await enroll(client, root, levels, geo.sections[102], recruiter=child["id"])
    await drain(owner_engine)

    one = (await client.get(f"{API}/members/{top['id']}/network", headers=root)).json()
    assert one["root"]["network"]["network_total"] == 3
    assert {n["member"]["id"] for n in one["items"]} == {child["id"], far["id"]}
    two = (
        await client.get(
            f"{API}/members/{top['id']}/network", headers=root, params={"max_depth": 2}
        )
    ).json()
    assert {n["member"]["id"] for n in two["items"]} == {child["id"], far["id"], grandchild["id"]}
    assert (
        await client.get(
            f"{API}/members/{top['id']}/network", headers=root, params={"max_depth": 4}
        )
    ).status_code == 422

    _, local = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    seen = (
        await client.get(
            f"{API}/members/{top['id']}/network", headers=local, params={"max_depth": 2}
        )
    ).json()
    assert {n["member"]["id"] for n in seen["items"]} == {child["id"], grandchild["id"]}
    assert seen["hidden"] == 1
    assert seen["root"]["network"]["network_total"] == 3  # totals include the hidden part


async def test_geographic_and_growth_statistics(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101], level="peace_builder")
    for section in (102, 103, 104):
        await enroll(client, root, levels, geo.sections[section], recruiter=top["id"])
    await drain(owner_engine)

    by_municipality = (
        await client.get(f"{API}/stats/geography", headers=root, params={"level": "municipality"})
    ).json()
    assert {row["node_id"]: row["active"] for row in by_municipality} == {
        geo.municipalities[1]: 2,
        geo.municipalities[2]: 2,
    }
    first = next(r for r in by_municipality if r["node_id"] == geo.municipalities[1])
    assert first["by_level"] == {"peace_builder": 1, "pacifier": 1}
    sections = (
        await client.get(
            f"{API}/stats/geography",
            headers=root,
            params={"level": "section", "municipality_id": geo.municipalities[2]},
        )
    ).json()
    assert sorted(row["label"] for row in sections) == ["Sección 0103", "Sección 0104"]

    _, local = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    mine = (await client.get(f"{API}/stats/geography", headers=local)).json()
    assert [row["active"] for row in mine] == [2]
    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    assert (await client.get(f"{API}/stats/geography", headers=capturist)).status_code == 403

    today = date.today()
    series = (
        await client.get(
            f"{API}/stats/growth",
            headers=root,
            params={"from": (today - timedelta(days=7)).isoformat(), "to": today.isoformat()},
        )
    ).json()
    assert series == [{"day": today.isoformat(), "enrollments": 4}]
    local_series = (
        await client.get(
            f"{API}/stats/growth",
            headers=local,
            params={
                "from": today.isoformat(),
                "to": today.isoformat(),
                "level_id": levels["pacifier"],
            },
        )
    ).json()
    assert local_series == [{"day": today.isoformat(), "enrollments": 1}]
    backwards = await client.get(
        f"{API}/stats/growth",
        headers=root,
        params={"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()},
    )
    assert backwards.status_code == 400


async def test_export_is_scoped_masked_and_logged(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101])
    await enroll(client, root, levels, geo.sections[103], recruiter=top["id"])
    full = await client.get(f"{API}/members-export", headers=root)
    assert full.status_code == 200
    assert full.headers["content-type"].startswith("text/csv")
    lines = full.text.strip().splitlines()
    assert lines[0].startswith("id,nombre,curp,nivel")
    assert len(lines) == 3
    assert "******" not in lines[1]  # root sees the full CURP

    _, viewer = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    masked = (await client.get(f"{API}/members-export", headers=viewer)).text.strip().splitlines()
    assert len(masked) == 2  # only municipality 1
    assert "******" in masked[1]
    logged = await rows(
        owner_engine,
        "SELECT details FROM audit.access_log WHERE action = 'export' ORDER BY occurred_at",
    )
    assert [entry["details"]["rows"] for entry in logged] == [2, 1]
    assert logged[1]["details"]["unmasked"] is False


def _cli_env(settings: Settings, monkeypatch: Any) -> None:
    for key, value in {
        "PAZ_DATABASE_URL": str(settings.database_url),
        "PAZ_MIGRATIONS_DATABASE_URL": str(settings.migrations_database_url),
        "PAZ_REDIS_URL": str(settings.redis_url),
        "PAZ_ENCRYPTION_KEYS": settings.encryption_keys.get_secret_value(),
        "PAZ_ENCRYPTION_ACTIVE_KEY_VERSION": str(settings.encryption_active_key_version),
        "PAZ_BLIND_INDEX_KEY": settings.blind_index_key.get_secret_value(),
        "PAZ_JWT_SECRET": settings.jwt_secret.get_secret_value(),
        "PAZ_ENVIRONMENT": "test",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


async def test_load_seed_and_aggregate_commands(
    geo: Geo,
    levels: dict[str, str],
    integration_settings: Settings,
    owner_engine: AsyncEngine,
    monkeypatch: Any,
) -> None:
    _cli_env(integration_settings, monkeypatch)
    mount_module_clis()
    runner = CliRunner()
    try:
        seeded = await asyncio.to_thread(
            runner.invoke, cli, ["peace-movement", "seed-load", "--members", "300"]
        )
        assert seeded.exit_code == 0, seeded.output
        assert await scalar(owner_engine, "SELECT count(*) FROM peace_movement.members") == 300
        assert await scalar(owner_engine, "SELECT max(depth) FROM peace_movement.members") >= 29
        rebuilt = await asyncio.to_thread(
            runner.invoke, cli, ["peace-movement", "aggregate", "--full"]
        )
        assert rebuilt.exit_code == 0, rebuilt.output
        assert "nodos: 300" in rebuilt.output
        # Every active member below a root counts once for that root.
        roots_total = await scalar(
            owner_engine,
            "SELECT sum(s.network_total + 1) FROM peace_movement.member_network_stats s "
            "JOIN peace_movement.members m ON m.id = s.member_id WHERE m.depth = 0",
        )
        assert roots_total == 300
        incremental = await asyncio.to_thread(runner.invoke, cli, ["peace-movement", "aggregate"])
        assert "Cambios: 0" in incremental.output
        monkeypatch.setenv("PAZ_ENVIRONMENT", "production")
        get_settings.cache_clear()
        refused = await asyncio.to_thread(
            runner.invoke, cli, ["peace-movement", "seed-load", "--members", "10"]
        )
        assert refused.exit_code == 1
    finally:
        get_settings.cache_clear()
