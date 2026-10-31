"""Activating a new framework (D-102, D-105): committees and coordinations follow their nodes by
natural key; what has no equivalent goes to the tray. In «Marco B» section 108 disappears and
municipality 2 changes its code, so it has no equivalent."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.geography.frameworks import activate_framework
from tests.integration.geography.conftest import Importer, scalar
from tests.integration.party_structure.conftest import API, Geo
from tests.integration.party_structure.test_appointments import _appoint, _person, _seats


async def _install(client: AsyncClient, root: dict[str, str], municipality: str) -> dict[str, Any]:
    catalog = (await client.get(f"{API}/catalog", headers=root)).json()
    municipal_type = next(b["id"] for b in catalog if b["code"] == "municipal_committee")
    response = await client.post(
        f"{API}/bodies",
        headers=root,
        json={
            "body_type_id": municipal_type,
            "municipality_id": municipality,
            "installed_on": "2026-01-01",
            "installation_agreement": "CDN/001/2026",
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def _grant_scopes(client: AsyncClient, root: dict[str, str], user_id: str) -> list[Any]:
    [grant] = (await client.get(f"/api/v1/users/{user_id}/grants", headers=root)).json()
    return [(s["level"], s["node_id"]) for s in grant["scopes"]]


async def test_activation_remaps_and_fills_the_tray(  # noqa: PLR0915, PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    run_import: Importer,
    owner_engine: AsyncEngine,
) -> None:
    kept = await _install(client, root, geo.municipalities[1])
    orphan = await _install(client, root, geo.municipalities[2])
    orphan_holder = await _appoint(
        client,
        root,
        (await _seats(client, root, orphan["id"]))["cdm_president"]["id"],
        await _person(client, root),
        access={"email": "presidencia.dos@example.com"},
    )
    coordination = (
        await client.post(
            f"{API}/coordinations",
            headers=root,
            json={
                "kind": "sectional",
                "name": "Centro",
                "node_ids": [geo.sections[101], geo.sections[108]],
                "created_on": "2026-01-01",
            },
        )
    ).json()
    coordinator = await _appoint(
        client,
        root,
        (await _seats(client, root, coordination["id"]))["sectional_coordinator"]["id"],
        await _person(client, root),
        access={"email": "coordinacion@example.com"},
    )

    await run_import(framework="Marco B", drop_section=108)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE geography.municipalities m SET municipality_code = 99 "
                "FROM geography.geographic_frameworks f WHERE f.id = m.framework_id "
                "AND f.name = 'Marco B' AND m.municipality_code = 2"
            )
        )
    async with owner_engine.begin() as connection:
        report = await activate_framework(connection, name="Marco B")
    counts = report.modules["party_structure"]
    assert counts["committees_municipality_id"] == 1
    assert counts["committees_without_territory"] == 1
    assert counts["coordination_section_id"] == 1
    assert counts["coordinations_with_lost_territory"] == 1

    def new(sql: str) -> str:
        return (
            "SELECT n.id FROM geography.{t} n JOIN geography.geographic_frameworks f "
            "ON f.id = n.framework_id WHERE f.name = 'Marco B' AND "
        ).format(t=sql.split(":", maxsplit=1)[0]) + sql.split(":")[1]

    municipality_1_b = str(
        await scalar(owner_engine, new("municipalities:n.municipality_code = 1"))
    )
    municipality_99_b = str(
        await scalar(owner_engine, new("municipalities:n.municipality_code = 99"))
    )
    section_101_b = str(await scalar(owner_engine, new("sections:n.section_number = 101")))

    body = (await client.get(f"{API}/bodies/{kept['id']}", headers=root)).json()
    assert body["municipality_id"] == municipality_1_b
    moved = (await client.get(f"{API}/coordinations/{coordination['id']}", headers=root)).json()
    assert [t["id"] for t in moved["territory"]] == [section_101_b]
    assert await _grant_scopes(client, root, coordinator["user_id"]) == [("section", section_101_b)]
    # The orphan committee keeps its holder, without territory or scope.
    assert await _grant_scopes(client, root, orphan_holder["user_id"]) == []

    # Only the national level sees and resolves the tray.
    state_b = str(await scalar(owner_engine, new("states:n.state_code = 1")))
    _, state_admin = await scoped(("admin",), [{"level": "state", "node_id": state_b}])
    assert (await client.get(f"{API}/territory-issues", headers=state_admin)).status_code == 403
    tray = (await client.get(f"{API}/territory-issues", headers=root)).json()
    by_kind = {issue["kind"]: issue for issue in tray}
    assert set(by_kind) == {"committee_without_territory", "coordination_nodes_removed"}
    assert by_kind["committee_without_territory"]["lost"][0]["label"] == "MUNICIPIO DOS"
    assert [n["label"] for n in by_kind["coordination_nodes_removed"]["lost"]] == ["Sección 108"]

    committee_issue = by_kind["committee_without_territory"]["id"]
    wrong = await client.post(
        f"{API}/territory-issues/{committee_issue}/resolve",
        headers=root,
        json={"action": "accept", "on": "2026-11-01"},
    )
    assert wrong.status_code == 400
    reassigned = await client.post(
        f"{API}/territory-issues/{committee_issue}/resolve",
        headers=root,
        json={"action": "reassign", "node_id": municipality_99_b, "on": "2026-11-01"},
    )
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["resolution"] == "reassign"
    assert reassigned.json()["body"]["municipality_id"] == municipality_99_b
    assert await _grant_scopes(client, root, orphan_holder["user_id"]) == [
        ("municipality", municipality_99_b)
    ]
    again = await client.post(
        f"{API}/territory-issues/{committee_issue}/resolve",
        headers=root,
        json={"action": "dissolve", "on": "2026-11-01"},
    )
    assert again.status_code == 409

    closed = await client.post(
        f"{API}/territory-issues/{by_kind['coordination_nodes_removed']['id']}/resolve",
        headers=root,
        json={"action": "close", "on": "2026-11-01", "notes": "Se reorganiza"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["body"]["status"] == "dissolved"
    ended = (
        await client.get(
            f"{API}/positions/{(await _seats(client, root, coordination['id']))['sectional_coordinator']['id']}/appointments",
            headers=root,
        )
    ).json()
    assert ended[0]["end_reason"] == "other"
    assert ended[0]["has_access"] is False
    assert (await client.get(f"{API}/territory-issues", headers=root)).json() == []
    assert (
        len(
            (
                await client.get(
                    f"{API}/territory-issues", headers=root, params={"include_resolved": True}
                )
            ).json()
        )
        == 2
    )
