"""Levels, goals with history, settings, zone coordinators and privacy notices (D-82, D-92)."""

import uuid
from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.testing import CliRunner

from app.cli import cli
from app.core.config import Settings, get_settings
from app.core.db.session import build_sessionmaker
from app.modules.peace_movement.catalog import coordinator_for_section, house_goal_for
from tests.integration.peace_movement.conftest import API, Geo


async def test_levels_are_seeded_in_order(
    client: AsyncClient, root: dict[str, str], levels: dict[str, str]
) -> None:
    listed = (await client.get(f"{API}/levels", headers=root)).json()
    assert [level["name"] for level in listed] == [
        "Pacificador",
        "Promotor de la Paz",
        "Mensajero de Paz",
        "Constructor de Paz",
        "Embajador de Paz",
    ]
    goals = (await client.get(f"{API}/level-goals", headers=root)).json()
    by_level = {g["level_id"]: (g["recruit_goal"], g["house_goal"]) for g in goals}
    assert by_level[levels["peace_ambassador"]] == (500, 5)
    assert by_level[levels["pacifier"]] == (1, None)


async def test_goals_keep_their_history(
    client: AsyncClient, root: dict[str, str], geo: Geo, levels: dict[str, str]
) -> None:
    def set_goal(**fields: Any) -> Any:
        return client.post(
            f"{API}/level-goals",
            headers=root,
            json={"level_id": levels["peace_messenger"], "state_id": geo.state, **fields},
        )

    first = await set_goal(recruit_goal=40, valid_from="2026-02-01")
    assert first.status_code == 201, first.text
    corrected = await set_goal(recruit_goal=45, valid_from="2026-02-01")
    assert corrected.json()["id"] == first.json()["id"]  # same day: a correction
    assert (await set_goal(recruit_goal=1, valid_from="2026-01-15")).status_code == 409
    later = await set_goal(recruit_goal=60)
    assert later.json()["valid_from"] == date.today().isoformat()

    history = (
        await client.get(
            f"{API}/level-goals", headers=root, params={"state_id": geo.state, "history": True}
        )
    ).json()
    mine = sorted((g for g in history if g["state_id"] == geo.state), key=lambda g: g["valid_from"])
    assert [(g["recruit_goal"], g["valid_to"]) for g in mine] == [
        (45, (date.today() - timedelta(days=1)).isoformat()),
        (60, None),
    ]
    # Without history: the national goals plus the state's current one.
    current = (
        await client.get(f"{API}/level-goals", headers=root, params={"state_id": geo.state})
    ).json()
    assert sum(1 for g in current if g["state_id"] == geo.state) == 1

    house = await client.post(
        f"{API}/house-goals", headers=root, json={"state_id": geo.state, "member_goal": 80}
    )
    assert house.status_code == 201
    houses = (
        await client.get(f"{API}/house-goals", headers=root, params={"state_id": geo.state})
    ).json()
    assert sorted(h["member_goal"] for h in houses) == [80, 100]
    bad_state = await client.post(
        f"{API}/house-goals", headers=root, json={"state_id": levels["pacifier"], "member_goal": 5}
    )
    assert bad_state.status_code == 400


async def test_settings(client: AsyncClient, root: dict[str, str], geo: Geo) -> None:
    current = (await client.get(f"{API}/settings", headers=root)).json()
    assert current == {
        "traffic_light_yellow_pct": 50,
        "traffic_light_green_pct": 100,
        "depth_alert_threshold": 50,
    }
    inverted = await client.put(
        f"{API}/settings",
        headers=root,
        json={
            "traffic_light_yellow_pct": 90,
            "traffic_light_green_pct": 80,
            "depth_alert_threshold": 20,
        },
    )
    assert inverted.status_code == 422
    updated = await client.put(
        f"{API}/settings",
        headers=root,
        json={
            "traffic_light_yellow_pct": 60,
            "traffic_light_green_pct": 90,
            "depth_alert_threshold": 30,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["depth_alert_threshold"] == 30


async def test_zone_coordinators(
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    owner_engine: AsyncEngine,
) -> None:
    whole, _ = await scoped(("coordinator",), [{"level": "state", "node_id": geo.state}])
    local, _ = await scoped(("coordinator",), [{"level": "state", "node_id": geo.state}])

    state_zone = await client.post(
        f"{API}/zone-coordinators",
        headers=root,
        json={
            "user_id": str(whole.id),
            "state_id": geo.state,
            "nodes": [{"level": "state", "node_id": geo.state}],
        },
    )
    assert state_zone.status_code == 201, state_zone.text
    assert state_zone.json()["section_count"] == 8
    municipal = await client.post(
        f"{API}/zone-coordinators",
        headers=root,
        json={
            "user_id": str(local.id),
            "state_id": geo.state,
            "nodes": [{"level": "municipality", "node_id": geo.municipalities[2]}],
        },
    )
    assert municipal.json()["section_count"] == 4
    assert municipal.json()["nodes"] == [
        {"level": "municipality", "node_id": geo.municipalities[2]}
    ]
    missing = await client.post(
        f"{API}/zone-coordinators",
        headers=root,
        json={
            "user_id": str(local.id),
            "state_id": geo.state,
            "nodes": [{"level": "section", "node_id": geo.municipalities[1]}],
        },
    )
    assert missing.status_code == 400

    async with build_sessionmaker(owner_engine)() as db:
        # The most specific zone wins; without a zone the credit stays pending.
        assert await coordinator_for_section(db, uuid.UUID(geo.sections[103])) == local.id
        assert await coordinator_for_section(db, uuid.UUID(geo.sections[101])) == whole.id
    ended = await client.post(f"{API}/zone-coordinators/{municipal.json()['id']}/end", headers=root)
    assert ended.json()["valid_to"] == date.today().isoformat()
    assert (
        await client.post(f"{API}/zone-coordinators/{municipal.json()['id']}/end", headers=root)
    ).status_code == 409
    async with build_sessionmaker(owner_engine)() as db:
        assert (
            await coordinator_for_section(
                db, uuid.UUID(geo.sections[103]), date.today() + timedelta(days=1)
            )
            == whole.id
        )
    listed = (
        await client.get(f"{API}/zone-coordinators", headers=root, params={"state_id": geo.state})
    ).json()
    assert len(listed) == 2  # the ended one is still in force today
    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    assert (
        await client.post(
            f"{API}/zone-coordinators",
            headers=capturist,
            json={"user_id": str(local.id), "state_id": geo.state, "nodes": []},
        )
    ).status_code == 403


async def test_privacy_notices(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    def publish(headers: dict[str, str], version: str) -> Any:
        return client.post(
            "/api/v1/people/privacy-notices",
            headers=headers,
            json={
                "code": "peace_movement",
                "version": version,
                "title": "Aviso del Movimiento de Paz",
                "body": f"Texto del aviso, versión {version}, de ejemplo para pruebas.",
            },
        )

    _, coordinator = await scoped(("coordinator",), [{"level": "national"}])
    assert (await publish(coordinator, "v1")).status_code == 403
    first = await publish(root, "v1")
    second = await publish(root, "v2")
    assert (await publish(root, "v2")).status_code == 409
    assert len(second.json()["body_sha256"]) == 64
    listed = (
        await client.get(
            "/api/v1/people/privacy-notices", headers=root, params={"code": "peace_movement"}
        )
    ).json()
    assert [(n["version"], n["valid_to"] is None) for n in listed] == [
        ("v2", True),
        ("v1", False),
    ]
    assert first.json()["is_sample"] is False


async def test_house_goals_and_resolution(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    owner_engine: AsyncEngine,
) -> None:
    def set_house(**fields: Any) -> Any:
        return client.post(
            f"{API}/house-goals", headers=root, json={"state_id": geo.state, **fields}
        )

    first = await set_house(member_goal=70, valid_from="2026-03-01")
    assert (await set_house(member_goal=75, valid_from="2026-03-01")).json()["id"] == first.json()[
        "id"
    ]
    assert (await set_house(member_goal=10, valid_from="2026-02-01")).status_code == 409
    await set_house(member_goal=90)
    national = await client.post(f"{API}/house-goals", headers=root, json={"member_goal": 120})
    assert national.json()["state_id"] is None
    history = (
        await client.get(
            f"{API}/house-goals", headers=root, params={"state_id": geo.state, "history": True}
        )
    ).json()
    assert sorted(h["member_goal"] for h in history) == [75, 90, 100, 120]

    async with build_sessionmaker(owner_engine)() as db:
        goal = await house_goal_for(db, uuid.UUID(geo.state))
        assert goal is not None
        assert goal.member_goal == 90  # the state's own goal wins over the national one
        old = await house_goal_for(db, uuid.UUID(geo.state), date(2026, 3, 15))
        assert old is not None
        assert old.member_goal == 75

    unknown = await client.post(
        f"{API}/level-goals", headers=root, json={"level_id": geo.state, "recruit_goal": 3}
    )
    assert unknown.status_code == 400
    zones = (
        await client.get(f"{API}/zone-coordinators", headers=root, params={"history": True})
    ).json()
    assert zones == []


def test_sample_notice_command(integration_settings: Settings, monkeypatch: Any) -> None:
    settings = integration_settings
    for key, value in {
        "PAZ_DATABASE_URL": str(settings.database_url),
        "PAZ_REDIS_URL": str(settings.redis_url),
        "PAZ_ENCRYPTION_KEYS": settings.encryption_keys.get_secret_value(),
        "PAZ_ENCRYPTION_ACTIVE_KEY_VERSION": str(settings.encryption_active_key_version),
        "PAZ_BLIND_INDEX_KEY": settings.blind_index_key.get_secret_value(),
        "PAZ_JWT_SECRET": settings.jwt_secret.get_secret_value(),
        "PAZ_ENVIRONMENT": "test",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        first = runner.invoke(cli, ["people", "sample-notice"])
        assert first.exit_code == 0, first.output
        assert "publicado" in first.output
        second = runner.invoke(cli, ["people", "sample-notice"])
        assert "Ya hay un aviso vigente" in second.output
        unknown = runner.invoke(cli, ["people", "sample-notice", "--code", "otro"])
        assert unknown.exit_code == 1
        monkeypatch.setenv("PAZ_ENVIRONMENT", "production")
        get_settings.cache_clear()
        assert runner.invoke(cli, ["people", "sample-notice"]).exit_code == 1
    finally:
        get_settings.cache_clear()
